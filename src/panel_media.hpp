// The Windows player saves the encoded streams, using one path pattern for the lenses.
struct RecordAttr {
    std::string path;
    std::vector<int> indices;
    int mode=1, reencode=0;
    std::shared_ptr<void> filter;
    std::function<std::shared_ptr<void>(int)> video_encoder,audio_encoder;
    int compression=0;
};
static_assert(sizeof(RecordAttr)==216 && offsetof(RecordAttr,mode)==56 && offsetof(RecordAttr,compression)==208);
struct RecordListener {
    virtual void progress(int,int64_t,int64_t,int64_t)=0;
    virtual void success(int,std::string)=0;
    virtual void error(int,std::shared_ptr<gwbase::Error>)=0;
    virtual void completed()=0;
};
struct RecordEvents final:RecordListener {
    std::atomic<bool> done{false};

    void progress(int,int64_t,int64_t,int64_t) override {}
    void success(int index,std::string) override {emit("clip_finalized",index);}
    void error(int,std::shared_ptr<gwbase::Error> e) override {emit("record_error",e?e->code:-1);}
    void completed() override {if(!done.exchange(true))emit("record_completed");}
};
struct Recorder {
    using Start=void(*)(void*,std::shared_ptr<RecordAttr>,std::shared_ptr<RecordListener>);
    using Stop=int(*)(void*);
    std::shared_ptr<RecordEvents> events;
    ULONGLONG since=0;
    bool stopping=false;
    void begin(HMODULE gw,void* player){
        if(events && !events->done)return;
        auto start=symbol<Start>(gw,"?start_record@APlayer@gwplayer@@QEAAXV?$shared_ptr@UVideoViewAttr@gwplayer@@@std@@V?$shared_ptr@VRecordListener@gwplayer@@@4@@Z");
        auto config=std::make_shared<RecordAttr>();
        // Only the integer lens placeholder is interpreted by the SDK.
        SYSTEMTIME t{};GetLocalTime(&t);char pattern[110]{};
        sprintf_s(pattern,"%04u-%02u-%02u_%02u-%02u-%02u-%03u_lente-%%d_",t.wYear,t.wMonth,t.wDay,t.wHour,t.wMinute,t.wSecond,t.wMilliseconds);
        FILE* tagfile=nullptr;char tag[33]{};
        if(fopen_s(&tagfile,"record.tag","rb") || !tagfile)throw std::runtime_error("record tag");
        auto n=fread(tag,1,32,tagfile);fclose(tagfile);
        if(n!=32 || strspn(tag,"0123456789abcdef")!=32)throw std::runtime_error("record tag");
        wchar_t dir[32768]{};
        DWORD len=GetEnvironmentVariableW(L"YOOSEE_CLIPS_PATH",dir,32768);
        if(!len || len>=32768)throw std::runtime_error("no recording folder");
        int bytes=WideCharToMultiByte(CP_UTF8,0,dir,len,nullptr,0,nullptr,nullptr);
        if(!bytes)throw std::runtime_error("recording folder encoding");
        std::string prefix(bytes,0);
        WideCharToMultiByte(CP_UTF8,0,dir,len,prefix.data(),bytes,nullptr,nullptr);
        for(char c:prefix){config->path+=c;if(c=='%')config->path+='%';}
        config->path+="/"+std::string(pattern)+tag+".mp4";
        events=std::make_shared<RecordEvents>();stopping=false;since=GetTickCount64();
        start(player,config,events);
        emit("record_started");
    }
    void poll(HMODULE gw,void* player){
        if(!events || events->done || GetTickCount64()-since<(stopping?120000u:10000u))return;
        if(!symbol<bool(*)(void*)>(gw,"?is_recording@APlayer@gwplayer@@QEAA_NXZ")(player)){
            if(!stopping)emit("record_error",-1);
            events->completed();
        }
    }
    void stop(HMODULE gw,void* player){
        if(!events || stopping || events->done)return;
        stopping=true;since=GetTickCount64();
        int rc=symbol<Stop>(gw,"?stop_record@APlayer@gwplayer@@QEAAHXZ")(player);
        emit("record_stop_result",rc);
    }
};
static HWND host_from_env(const wchar_t* key){
    wchar_t s[32]{};if(!GetEnvironmentVariableW(key,s,32))return nullptr;
    return reinterpret_cast<HWND>(static_cast<uintptr_t>(_wcstoui64(s,nullptr,10)));
}
