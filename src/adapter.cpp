#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>
#include <mmsystem.h>
#include <chrono>
#include <deque>
#include <typeinfo>
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <string>
#include <atomic>
#include <mutex>
#include "iot_abi.hpp"
#include "decode_audio.hpp"

static SRWLOCK result_lock=SRWLOCK_INIT;
static void output(const std::string& line);
static HANDLE result_handle = INVALID_HANDLE_VALUE;
static void emit(const char* stage, int code=0) {
    char out[192]; int n=snprintf(out,sizeof out,"{\"stage\":\"%s\",\"code\":%d}\n",stage,code);
    output(std::string(out,(size_t)n));
}
static void output(const std::string& line) {
    AcquireSRWLockExclusive(&result_lock);
    DWORD done=0;
    while(done<line.size()){
        DWORD n=0;if(!WriteFile(result_handle,line.data()+done,(DWORD)(line.size()-done),&n,nullptr)||!n)break;
        done+=n;
    }
    ReleaseSRWLockExclusive(&result_lock);
}
struct QueryState { std::atomic<int> done{0}; };
static int perform_request(HMODULE module,const std::string& device,int light=-1) {
    auto factory=reinterpret_cast<iotvideo::MessageFactory>(GetProcAddress(module,iotvideo::message_export));
    if(!factory){emit("message_factory_missing");return 40;}
    auto mgr=factory();if(!mgr){emit("message_factory_null");return 41;}
    emit("message_factory_ready");
    auto state=std::make_shared<QueryState>();
    const bool is_light=light>=0;
    auto callback=std::make_shared<iotvideo::IMessageCallback>();
    callback->on_send=[is_light](unsigned int) { emit(is_light?"light_sent":"property_sent");return iotvideo::IMessageCallback::CONTINUE; };
    callback->on_ack=[is_light](std::vector<unsigned char>,std::int64_t) {
        emit(is_light?"light_ack":"property_ack");return iotvideo::IMessageCallback::CONTINUE;
    };
    callback->on_error=[state,is_light](std::shared_ptr<gwbase::Error> error) {
        int expected=0;if(state->done.compare_exchange_strong(expected,-1)) {
            emit(is_light?"light_error":"property_error",error?error->code:0);
            if(error)emit(is_light?"light_error_category":"property_error_category",error->cat);
            state->done.store(2);
        }
        return iotvideo::IMessageCallback::FINISHED;
    };
    callback->on_recv_data=[state,is_light](std::vector<unsigned char> data,std::int64_t) {
        int expected=0;
        if(state->done.compare_exchange_strong(expected,-1)){
            if(data.size()>65536){emit(is_light?"light_response_too_large":"property_response_too_large");state->done.store(3);}
            else {
                // Private pipe to Python. This payload must never enter the shareable report.
                static const char digits[]="0123456789abcdef";
                std::string line=is_light?"{\"stage\":\"light_payload\",\"hex\":\"":"{\"stage\":\"property_payload\",\"hex\":\"";
                line.reserve(data.size()*2+64);
                for(unsigned char c:data){line.push_back(digits[c>>4]);line.push_back(digits[c&15]);}
                line+="\"}\n";output(line);
                emit(is_light?"light_received":"property_received",(int)data.size());state->done.store(1);
            }
        }
        return iotvideo::IMessageCallback::FINISHED;
    };
    emit(is_light?"light_command_started":"property_query_started");
    // Zero selects the SDK's default handle timeout (verified in its implementation).
    if(light<0)mgr->read_property_of_device(device,iotvideo::online_property,0,callback);
    else {
        const std::string json=light ? "{\"type\":11,\"data\":{\"whiteLightCtrl\":1,\"whiteLightStatus\":0}}" : "{\"type\":11,\"data\":{\"whiteLightCtrl\":0,\"whiteLightStatus\":0}}";
        // Android json2Bytes encodes UTF-8 without a trailing NUL/header.
        // Its default path requests a response and continues waiting after ACK.
        std::vector<unsigned char> payload(json.begin(),json.end());
        mgr->send_msg_to_device(device,payload,0,true,true,0,callback);
    }
    ULONGLONG start=GetTickCount64();
    while(GetTickCount64()-start<20000){int done=state->done.load();if(done>0)return done==1?0:43;Sleep(50);}
    emit(is_light?"light_timeout":"property_timeout");return 44;
}
#include "live_preview.hpp"
static bool read_line(std::string& out, size_t maxlen) {
    out.clear(); int c;
    while ((c=getchar())!=EOF && c!='\n') {
        if(c=='\r') continue;
        if(out.size()>=maxlen) return false;
        out.push_back((char)c);
    }
    return !out.empty();
}
static bool verify_hash(const std::wstring& file,const unsigned char (&expected)[32]) {
    HANDLE f=CreateFileW(file.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,0,nullptr);
    if(f==INVALID_HANDLE_VALUE) return false;
    BCRYPT_ALG_HANDLE alg=nullptr; BCRYPT_HASH_HANDLE hash=nullptr;
    unsigned char digest[32]={}; bool ok=BCryptOpenAlgorithmProvider(&alg,BCRYPT_SHA256_ALGORITHM,nullptr,0)==0;
    if(ok) ok=BCryptCreateHash(alg,&hash,nullptr,0,nullptr,0,0)==0;
    unsigned char data[65536]; DWORD n=0;
    while(ok) { if(!ReadFile(f,data,sizeof data,&n,nullptr)){ok=false;break;} if(!n)break;
        ok=BCryptHashData(hash,data,n,0)==0; }
    if(ok)ok=BCryptFinishHash(hash,digest,32,0)==0;
    if(hash)BCryptDestroyHash(hash); if(alg)BCryptCloseAlgorithmProvider(alg,0); CloseHandle(f);

    return ok && memcmp(expected,digest,32)==0;
}
static int run(int argc,wchar_t** argv) {
    if(argc!=3 || (wcscmp(argv[2],L"--probe") && wcscmp(argv[2],L"--session") && wcscmp(argv[2],L"--read") && wcscmp(argv[2],L"--light-on") && wcscmp(argv[2],L"--light-off") && wcscmp(argv[2],L"--light-menu") && wcscmp(argv[2],L"--video"))) {emit("arguments_invalid");return 10;}
    wchar_t absolute[32768];
    DWORD len=GetFullPathNameW(argv[1],32768,absolute,nullptr);
    if(!len || len>=32768){emit("path_invalid");return 11;}
    std::wstring folder(absolute),dll=folder+L"\\IOT_LIB.dll";
    const unsigned char sdk_hash[]={0xec,0x07,0xcb,0x4b,0x98,0xbc,0x48,0x6e,0x8b,0xdb,0x05,0x8c,0x86,0x95,0xd1,0x6f,0x0f,0xb2,0xc5,0x24,0xbe,0x50,0xdd,0x8c,0x9d,0x0f,0x0c,0xfa,0x87,0xfa,0x09,0x90};
    const unsigned char player_hash[]={0x62,0x2e,0x31,0xd0,0x42,0x81,0x82,0xd5,0x3e,0xdb,0xab,0xeb,0x53,0xaa,0xb7,0xe0,0x95,0xac,0x94,0x40,0x53,0xa1,0xb9,0x0f,0xf9,0xd3,0x79,0xcc,0x8b,0x75,0xc2,0xd2};
    if(!wcscmp(argv[2],L"--video") && !verify_hash(folder+L"\\GWPlayerLibV1.dll",player_hash)){emit("video_library_missing");return 60;}
    if(!verify_hash(dll,sdk_hash)){emit("sdk_hash_mismatch");return 12;}
    emit("sdk_verified");
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX|SEM_NOOPENFILEERRORBOX);
    if(!SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_SYSTEM32|LOAD_LIBRARY_SEARCH_USER_DIRS) || !AddDllDirectory(folder.c_str())){
        emit("search_path_failed",(int)GetLastError());return 13;
    }
    HMODULE module=LoadLibraryExW(dll.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32|LOAD_LIBRARY_SEARCH_USER_DIRS);
    if(!module){emit("load_failed",(int)GetLastError());return 14;}
    // Keep module loaded through process exit: SDK may own background threads.
    emit("sdk_loaded");
    auto factory=reinterpret_cast<iotvideo::InitializerFactory>(GetProcAddress(module,iotvideo::initializer_export));
    if(!factory){emit("factory_missing");return 15;}
    auto initializer=factory();
    if(!initializer){emit("factory_null");return 16;}
    emit("factory_ready");
    emit("initial_state",(int)initializer->link_state());
    if(!wcscmp(argv[2],L"--probe")){emit("probe_ok");return 0;}
    std::string id,token;
    if(!read_line(id,20)||!read_line(token,16384)){emit("session_input_invalid");return 17;}
    for(char c:id)if(c<'0'||c>'9'){emit("session_input_invalid");return 17;}
    char* end=nullptr; errno=0; auto access_id=_strtoui64(id.c_str(),&end,10);
    if(errno || !access_id || !end || *end){emit("session_input_invalid");return 17;}
    std::string device;
    const int light=!wcscmp(argv[2],L"--light-on")?1:(!wcscmp(argv[2],L"--light-off")?0:-1);
    const bool menu=!wcscmp(argv[2],L"--light-menu");
    const bool video=!wcscmp(argv[2],L"--video");
    const bool query=video || menu || !wcscmp(argv[2],L"--read") || light>=0;
    if(query){
        if(!read_line(device,128)){emit("device_input_invalid");return 18;}
        for(unsigned char c:device)if(!((c>='0'&&c<='9')||(c>='A'&&c<='Z')||(c>='a'&&c<='z')||c=='_'||c=='-')){
            emit("device_input_invalid");return 18;
        }
    }
    iotvideo::InitializerParams params;
    params.access_id=access_id;params.access_token=token;
    params.iv_host="|list.iotvideo.cloudlinks.cn";
    SecureZeroMemory(token.data(),token.size());token.clear();
    initializer->register_p2p(params);
    SecureZeroMemory(params.access_token.data(),params.access_token.size());params.access_token.clear();
    emit("registration_started");
    ULONGLONG start=GetTickCount64(); int previous=-999,result=21;
    while(GetTickCount64()-start<30000){
        int state=(int)initializer->link_state();
        if(state!=previous){emit("session_state",state);previous=state;}
        if(state==1){emit("session_online");result=0;break;}
        if(state>=3){emit("session_rejected",state);result=20;break;}
        Sleep(200);
    }
    if(result==21)emit("session_timeout");
    if(result==0 && video)result=preview::run_video(module,device);
    else if (result == 0 && menu) {
        std::string command;
        while (read_line(command, 8)) {
            if (command != "on" && command != "off") {
                result = 10;
                break;
            }
            int link = (int)initializer->link_state();
            emit("session_state", link);
            if (link != 1) {
                result = 20;
            } else {
                result = perform_request(module, device, command == "on" ? 1 : 0);
            }
            emit("command_done", result);
            // Close on failure so late callbacks cannot enter a later request.
            if (result != 0) break;
        }
    } else if (result == 0 && query) {
        result = perform_request(module, device, light);
    }
    initializer->unregister_p2p(false);
    emit("unregister_requested");
    Sleep(500);
    return result;
}
int wmain(int argc,wchar_t** argv) {
    if(argc==4 && !wcscmp(argv[1],L"--decode-audio"))return decode_file(argv[2],argv[3]);
    // Vendor stdout/stderr are discarded, not copied into the shareable result.
    DuplicateHandle(GetCurrentProcess(),GetStdHandle(STD_OUTPUT_HANDLE),GetCurrentProcess(),&result_handle,0,FALSE,DUPLICATE_SAME_ACCESS);
    FILE* dummy=nullptr;freopen_s(&dummy,"NUL","w",stdout);freopen_s(&dummy,"NUL","w",stderr);
    int rc=30;try{rc=run(argc,argv);}catch(...){emit("native_exception");}
    // Teardown of SDK global threads is not reconstructed. OS reclaims the short-lived worker.
    ExitProcess((UINT)rc);
}
