// Windows Yoosee 1.0.0.14, Microsoft STL /MD x64. See NOTAS_VIDEO.md.
#include <array>
#include "talk_burst.hpp"
#include "loop_audio.hpp"
#include <algorithm>
#include <thread>
#include <stdexcept>
namespace preview {
struct Live;
struct alignas(8) View { unsigned char data[952]; };
using Create = std::shared_ptr<Live>(*)(std::string,int,int);
using Construct = void(*)(View*,int);
using Destroy = void(*)(View*);
using SetIndex = void(*)(View*,int);
using Bind = void(*)(View*,HWND,int);
using Attach = void(*)(void*,std::shared_ptr<View>);
using State = int(*)(void*);
using Mute = void(*)(void*,bool);
template<class T> T symbol(HMODULE module,const char* name) {
    auto addr=GetProcAddress(module,name);
    if(!addr) throw std::runtime_error("missing player export");
    return reinterpret_cast<T>(addr);
}
#include "preview_audio.hpp"
struct Api {
    using AudioAttach=void(*)(void*,std::shared_ptr<Speaker>);
    AudioAttach audio_attach;
    Create create;
    Construct construct;
    Destroy destroy,start,stop;
    SetIndex stream_index;
    Bind bind;
    Attach add,remove;
    State state;
    Mute mute;
    Api(HMODULE sdk,HMODULE gw):
      audio_attach(symbol<AudioAttach>(gw,"?set_audio_render@APlayer@gwplayer@@QEAAXV?$shared_ptr@VAbstractAudioRenderer@gwplayer@@@std@@@Z")),
      create(symbol<Create>(sdk,"?create@ILivePlayer@iotvideo@@SA?AV?$shared_ptr@VILivePlayer@iotvideo@@@std@@V?$basic_string@DU?$char_traits@D@std@@V?$allocator@D@2@@4@HH@Z")),
      construct(symbol<Construct>(gw,"??0WinVideoRenderView@gwplayer@@QEAA@H@Z")),
      destroy(symbol<Destroy>(gw,"??1WinVideoRenderView@gwplayer@@UEAA@XZ")),
      start(symbol<Destroy>(gw,"?start@WinVideoRenderView@gwplayer@@QEAAXXZ")),
      stop(symbol<Destroy>(gw,"?stop@WinVideoRenderView@gwplayer@@QEAAXXZ")),
      stream_index(symbol<SetIndex>(gw,"?setStreamIndex@VideoRenderView@gwplayer@@QEAAXH@Z")),
      bind(symbol<Bind>(gw,"?CreateRnederMode@WinVideoRenderView@gwplayer@@QEAAXPEAUHWND__@@H@Z")),
      add(symbol<Attach>(gw,"?add_video_view@APlayer@gwplayer@@QEAAXV?$shared_ptr@VVideoRenderView@gwplayer@@@std@@@Z")),
      remove(symbol<Attach>(gw,"?remove_video_view@APlayer@gwplayer@@QEAAXV?$shared_ptr@VVideoRenderView@gwplayer@@@std@@@Z")),
      state(symbol<State>(gw,"?get_state@APlayer@gwplayer@@QEAA?AW4PlaybackState@2@XZ")),
      mute(symbol<Mute>(gw,"?set_mute@APlayer@gwplayer@@QEAAX_N@Z")) {}
};
constexpr int lens_count=2;
struct RenderedLens {
    Api& api;
    void* player;
    std::shared_ptr<View> view;
    bool started=false, attached=false;
    RenderedLens(Api& a,void* p): api(a),player(p) {}
    void open(HWND surface,int index) {
        auto storage=std::make_unique<View>();
        api.construct(storage.get(),index);
        view=std::shared_ptr<View>(storage.release(),[destroy=api.destroy](View* v){destroy(v);::operator delete(v);});
        api.bind(view.get(),surface,2);
        api.stream_index(view.get(),index);
        api.start(view.get());
        started=true;
        api.add(player,view);
        attached=true;
        emit("video_view_attached",index);
    }
    void close() {
        if(started){api.stop(view.get());started=false;}
        if(attached){api.remove(player,view);attached=false;}
        view.reset();
    }
    ~RenderedLens(){close();}
    RenderedLens(const RenderedLens&)=delete;
};
// Windows 1.0.0.14: IConnection::send_data_args (PDB record 0x6E52).
struct DirectionData {
    uint64_t category=0;
    uint8_t type=3;
    std::vector<unsigned char> data;
    uint16_t camera=0;
    bool sequence=false;
    int64_t timeout=10000000;
    std::shared_ptr<void> callback;
    uint64_t batch=1;
    int64_t pts=0;
    bool keyframe=false;
};
static_assert(sizeof(DirectionData)==96 && offsetof(DirectionData,data)==16 &&
              offsetof(DirectionData,timeout)==48 && offsetof(DirectionData,keyframe)==88);
static std::shared_ptr<void> player_connection(void* player) {
    // MSVC instance method returning shared_ptr: this in RCX, return storage in RDX.
    using Handle=std::shared_ptr<void>;
    alignas(Handle) unsigned char storage[sizeof(Handle)];
    auto table=*reinterpret_cast<void***>(player);
    using GetConnection=Handle*(*)(void*,void*);
    auto returned=reinterpret_cast<GetConnection>(table[19])(player,storage);
    Handle connection=std::move(*returned);
    returned->~Handle();
    return connection;
}
static int move_once(void* player,int index) {
    static constexpr const char* steps[]={
        R"({"type":2,"data":{"dir":0}})",R"({"type":2,"data":{"dir":1}})",
        R"({"type":2,"data":{"dir":2}})",R"({"type":2,"data":{"dir":3}})"};
    if(!player || index<0 || index>=4)return -1;
    DirectionData data;
    const auto json=steps[index];
    data.data.assign(json,json+std::strlen(json));
    auto connection=player_connection(player);
    if(!connection)return -1;
    using Send=int(*)(void*,const DirectionData&);
    auto send=reinterpret_cast<Send>((*reinterpret_cast<void***>(connection.get()))[7]);
    return send(connection.get(),data);
}
#include "panel_media.hpp"
struct Window {
    HMODULE sdk;
    const std::string& device;
    Api& api;
    Window(HMODULE m,const std::string& d,Api& a): sdk(m),device(d),api(a) {}
    HWND hwnd{}, label{}, on{}, off{}, listen_button{},talk_button{},audio_label{};
    std::shared_ptr<Speaker> speaker=std::make_shared<Speaker>();
    std::unique_ptr<Talk> talk;
    HMODULE gw{};
    Live* live{};
    bool listening=false;
    unsigned talk_seconds=0;
    std::array<HWND,2> hosts{};
    bool embedded=false,light_on=false,alert=false,flashed=false,restore=false,prior_light=false;
    ULONGLONG next_flash=0;
    Recorder recorder;
    static constexpr UINT panel_command=WM_APP+50;
    void request_light(bool value){
        int id=value?1:2;
        SendMessageW(hwnd,WM_COMMAND,id,reinterpret_cast<LPARAM>(value?on:off));
    }
    void settle(){
        if(command.joinable())return;
        if(restore){restore=false;request_light(prior_light);return;}
        if(closing && (!recorder.events || recorder.events->done || GetTickCount64()-close_started>=120000))
            PostQuitMessage(0);
    }
    void dispatch_panel(int id){
        if(closing)return;
        if(id==11){SendMessageW(hwnd,WM_CLOSE,0,0);return;}
        if(id==10 || id==12){
            if(id==12)recorder.stop(gw,player);
            else if(last_state==5)recorder.begin(gw,player);
            return;
        }
        if(id==9 && alert){stop_talk();settle();return;}
        if(last_state!=5)return;
        if(id==9 && !talk && !command.joinable() && !restore){
            prior_light=light_on;alert=true;flashed=false;next_flash=0;
            audio_command(8);
            if(talk)emit("alert_state",1);
            else {alert=false;emit("alert_state",0);}
            return;
        }
        if(id==7 && !talk){audio_command(id);return;}
        if(id==8 && !alert){audio_command(id);return;}
        if(id>=1 && id<=6 && !alert && !restore && !command.joinable()){
            auto button=id<=2?(id==1?on:off):arrows[id-3];
            SendMessageW(hwnd,WM_COMMAND,id,reinterpret_cast<LPARAM>(button));
        }
    }
    void stop_talk(const wchar_t* message=L"Interfone encerrado") {
        if(!talk)return;
        talk.reset();talk_seconds=0;
        emit("talk_active",0);
        if(alert){alert=false;restore=flashed;emit("alert_state",0);}
        if(listening && !closing){speaker->enable(true);api.mute(player,false);}
        SetWindowTextW(talk_button,L"Falar por 5 s");
        SetWindowTextW(audio_label,message);
        update_buttons();
    }
    void audio_command(int id) {
        if(!player || last_state!=5 || closing)return;
        if(id==7 && !talk){
            listening=!listening;
            speaker->enable(listening);api.mute(player,!listening);
            emit("audio_listen",listening?1:0);
            SetWindowTextW(listen_button,listening?L"Silenciar câmera":L"Ouvir câmera");
            SetWindowTextW(audio_label,listening?L"Escuta ligada":L"Escuta desligada");
        } else if(id==8){
            if(talk){stop_talk();return;}
            emit("talk_requested");
            try {
                auto conn=player_connection(player);
                // The original client casts IConnection to Connection before
                // constructing Intercom. Both base addresses coincide in this SDK.
                struct HasRtti { virtual void marker()=0; };
                auto typed=reinterpret_cast<HasRtti*>(conn.get());
                if(!typed || std::strcmp(typeid(*typed).raw_name(),".?AVConnection@iotvideo@@")!=0)
                    throw std::runtime_error("connection type");
                talk=std::make_unique<Talk>(sdk,gw,live,std::move(conn),alert);
                speaker->enable(false);api.mute(player,true);
                if(!talk->begin()){stop_talk();SetWindowTextW(audio_label,L"Falha ao iniciar interfone");return;}
                emit("talk_active",1);
                SetWindowTextW(talk_button,L"Parar");
                SetWindowTextW(audio_label,L"Abrindo microfone…");
                update_buttons();
            } catch(...) {
                stop_talk(); emit("talk_setup_error");SetWindowTextW(audio_label,L"Falha ao abrir interfone");
            }
        }
    }
    std::array<HWND,lens_count> surfaces{};
    std::array<HWND,4> arrows{};
    void update_buttons() {
        bool available=!closing && !command.joinable();
        EnableWindow(listen_button,!closing && last_state==5 && !talk);
        EnableWindow(talk_button,!closing && last_state==5);
        EnableWindow(on,available);EnableWindow(off,available);
        for(auto button:arrows)EnableWindow(button,available && last_state==5);
    }
    void* player{};
    int last_state=-1;
    std::thread command;
    bool closing=false;
    ULONGLONG close_started=0;
    static constexpr UINT light_done=WM_APP+1;
    static LRESULT CALLBACK proc(HWND h,UINT msg,WPARAM w,LPARAM l) {
        Window* self=reinterpret_cast<Window*>(GetWindowLongPtrW(h,GWLP_USERDATA));
        if(msg==WM_NCCREATE) {
            self=static_cast<Window*>(reinterpret_cast<CREATESTRUCTW*>(l)->lpCreateParams);
            SetWindowLongPtrW(h,GWLP_USERDATA,reinterpret_cast<LONG_PTR>(self));
        }
        if(!self)return DefWindowProcW(h,msg,w,l);
        switch(msg) {
        case panel_command:
            try{if(self->embedded && self->player)self->dispatch_panel(static_cast<int>(w));}
            catch(...){emit("panel_command_error",static_cast<int>(w));}
            return 0;
        case WM_TIMER: {
            if(!self->player)break;
            if(w==2){
                if(self->talk){
                    try{
                        if(!self->talk->tick()){
                            self->stop_talk(self->talk->stop_message());
                            return 0;
                        }
                        unsigned seconds=self->talk->mic->seconds_left();
                        if(seconds && seconds!=self->talk_seconds){
                            self->talk_seconds=seconds;emit("talk_seconds",seconds);
                            wchar_t text[32]{};
                            swprintf_s(text,L"Fale agora (%u s)",seconds);
                            SetWindowTextW(self->audio_label,text);
                        }
                    }catch(...){emit("mic_error",-1);self->stop_talk(L"Falha no envio de voz");}
                }
                return 0;
            }
            if(self->embedded){
                for(size_t i=0;i<self->hosts.size();++i){
                    if(!IsWindow(self->hosts[i])){SendMessageW(h,WM_CLOSE,0,0);return 0;}
                    RECT rect{}, child{};GetClientRect(self->hosts[i],&rect);GetClientRect(self->surfaces[i],&child);
                    if(rect.right!=child.right || rect.bottom!=child.bottom)
                        MoveWindow(self->surfaces[i],0,0,rect.right,rect.bottom,TRUE);
                }
                self->settle();self->recorder.poll(self->gw,self->player);
            }
            int state=self->api.state(self->player);
            if(state!=self->last_state){
                if(state!=5)self->stop_talk();
                self->last_state=state;self->update_buttons();emit("video_state",state);
                const wchar_t* title=state==5?L"Minha câmera | Reproduzindo":state==10?L"Minha câmera | Erro ao abrir vídeo":L"Minha câmera | Conectando vídeo";
                SetWindowTextW(h,title);
            }
            if(self->alert && self->talk && self->talk->mic->started() &&
               !self->command.joinable() && GetTickCount64()>=self->next_flash){
                self->flashed=true;self->request_light(!self->light_on);
            }
            return 0;
        }
        case WM_COMMAND: {
            int id=LOWORD(w);
            if((id==7 || id==8) && l && HIWORD(w)==BN_CLICKED){self->audio_command(id);return 0;}
            bool direction=id>=3 && id<=6;
            if((id!=1 && id!=2 && !direction)||!l||HIWORD(w)!=BN_CLICKED||self->command.joinable())break;
            if(direction && self->last_state!=5)break;
            EnableWindow(self->on,FALSE);EnableWindow(self->off,FALSE);
            SetWindowTextW(self->label,direction?L"Enviando movimento…":L"Aguardando resposta da luz…");
            emit("control_busy",id);
            self->command=std::thread([self,h,id,direction]{
                int rc=30;
                try {
                    if(direction){
                        emit("ptz_direction",id-3);
                        rc=move_once(self->player,id-3);
                        emit("ptz_send_result",rc);
                    } else {
                        emit("preview_light",id);
                        rc=perform_request(self->sdk,self->device,id==1?1:0);
                    }
                } catch(...) {if(direction) emit("ptz_send_result",rc);}
                PostMessageW(h,light_done,rc,id);
            });
            self->update_buttons();
            return 0;
        }
        case light_done:
            if(self->command.joinable())self->command.join();
            if(l==1 || l==2){
                if(!w){self->light_on=l==1;emit("light_state",self->light_on?1:0);}
                else {emit("panel_light_error",static_cast<int>(w));if(self->alert)self->stop_talk();}
                self->next_flash=GetTickCount64()+1000;
            }
            emit("control_busy",0);
            if(l>=3)SetWindowTextW(self->label,w==0?L"Movimento enviado":L"Confira o movimento na imagem");
            else SetWindowTextW(self->label,w==0?L"Resposta da luz recebida":L"Sem confirmação da luz");
            self->update_buttons();
            self->settle();
            return 0;
        case WM_CLOSE:
            if(!self->closing)self->close_started=GetTickCount64();
            self->closing=true;self->stop_talk();
            if(self->player && self->recorder.events)self->recorder.stop(self->gw,self->player);
            if(self->command.joinable())SetWindowTextW(self->label,L"Encerrando após o comando…");
            else self->settle();
            return 0;
        }
        return DefWindowProcW(h,msg,w,l);
    }
    ~Window() {
        if(command.joinable())command.join();
        if(embedded)for(auto child:surfaces)if(IsWindow(child))DestroyWindow(child);
        if(hwnd)DestroyWindow(hwnd);
    }
    HWND child(const wchar_t* cls,const wchar_t* title,DWORD style,int x,int y,int width,int height,int id=0) {
        HWND h=CreateWindowExW(0,cls,title,WS_CHILD|WS_VISIBLE|style,x,y,width,height,hwnd,
                                reinterpret_cast<HMENU>(static_cast<INT_PTR>(id)),GetModuleHandleW(nullptr),nullptr);
        if(!h)throw std::runtime_error("window");
        SendMessageW(h,WM_SETFONT,reinterpret_cast<WPARAM>(GetStockObject(DEFAULT_GUI_FONT)),TRUE);
        return h;
    }
    void open() {
        WNDCLASSW cls{};cls.lpfnWndProc=proc;cls.hInstance=GetModuleHandleW(nullptr);
        cls.hCursor=LoadCursorW(nullptr,MAKEINTRESOURCEW(32512));cls.hbrBackground=(HBRUSH)(COLOR_WINDOW+1);
        cls.lpszClassName=L"YooseeLivePreview";if(!RegisterClassW(&cls))throw std::runtime_error("class");
        DWORD style=WS_OVERLAPPED|WS_CAPTION|WS_SYSMENU|WS_MINIMIZEBOX|WS_CLIPCHILDREN;
        RECT work{0,0,800,720};
        SystemParametersInfoW(SPI_GETWORKAREA,0,&work,0);
        RECT frame{};AdjustWindowRect(&frame,style,FALSE);
        const int footer=134;
        const int max_height=work.bottom-work.top-(frame.bottom-frame.top)-footer-20;
        const int max_width=work.right-work.left-(frame.right-frame.left)-20;
        const int height=std::max(1,std::min({360,max_height/lens_count,max_width*9/16}));
        const int width=height*16/9;
        const int controls_y=lens_count*height+10;
        RECT area{0,0,width,lens_count*height+footer};AdjustWindowRect(&area,style,FALSE);
        hwnd=CreateWindowW(cls.lpszClassName,L"Minha câmera | Abrindo vídeo",style,CW_USEDEFAULT,CW_USEDEFAULT,
                          area.right-area.left,area.bottom-area.top,nullptr,nullptr,cls.hInstance,this);
        if(!hwnd)throw std::runtime_error("window");
        hosts={host_from_env(L"YOOSEE_HOST_A"),host_from_env(L"YOOSEE_HOST_B")};
        embedded=hosts[0] && hosts[1];
        for(int i=0;i<lens_count;++i)
            if(embedded){
                RECT r{};if(!GetClientRect(hosts[i],&r))throw std::runtime_error("display host");
                surfaces[i]=CreateWindowW(L"STATIC",L"",WS_CHILD|WS_VISIBLE|SS_BLACKRECT,0,0,std::max(1L,r.right),std::max(1L,r.bottom),hosts[i],nullptr,cls.hInstance,nullptr);
                if(!surfaces[i])throw std::runtime_error("display surface");
            }else surfaces[i]=child(L"STATIC",L"",SS_BLACKRECT,0,i*height,width,height);
        on=child(L"BUTTON",L"Ligar luz",BS_PUSHBUTTON,12,controls_y,106,32,1);
        off=child(L"BUTTON",L"Desligar luz",BS_PUSHBUTTON,128,controls_y,106,32,2);
        label=child(L"STATIC",L"Luz branca",SS_CENTERIMAGE,252,controls_y,std::max(1,width-260),32);
        const wchar_t* directions[]={L"← Esquerda",L"Direita →",L"↑ Cima",L"↓ Baixo"};
        const int button_width=(width-24)/4;
        for(int i=0;i<4;++i)
            arrows[i]=child(L"BUTTON",directions[i],BS_PUSHBUTTON,12+i*button_width,controls_y+40,button_width-4,32,3+i);
        const int audio_width=std::min(132,(width-32)/3);
        listen_button=child(L"BUTTON",L"Ouvir câmera",BS_PUSHBUTTON,12,controls_y+80,audio_width,32,7);
        talk_button=child(L"BUTTON",L"Falar por 5 s",BS_PUSHBUTTON,16+audio_width,controls_y+80,audio_width,32,8);
        audio_label=child(L"STATIC",L"Áudio desligado",SS_CENTERIMAGE,24+2*audio_width,controls_y+80,std::max(1,width-28-2*audio_width),32);
        update_buttons();
        if(!embedded){ShowWindow(hwnd,SW_SHOW);UpdateWindow(hwnd);}
        else output("{\"stage\":\"panel_ready\",\"code\":"+std::to_string(reinterpret_cast<uintptr_t>(hwnd))+"}\n");
    }
};
static int run_video(HMODULE sdk,const std::string& device) {
    auto gw=GetModuleHandleW(L"GWPlayerLibV1.dll");
    if(!gw){emit("video_library_missing");return 60;}
    try {
        Api api(sdk,gw);
        Window win{sdk,device,api};
        win.open();emit("video_window_ready");
        auto live=api.create(device,0,0);
        if(!live){emit("video_create_failed");return 61;}
        emit("video_player_created");
        // Client setRender/play access the IPlayer virtual base via vbptr+8, entry 1.
        auto vb=reinterpret_cast<char*>(live.get())+8;
        void* player=vb+(*reinterpret_cast<const int32_t**>(vb))[1];
        auto slots=*reinterpret_cast<void***>(player);
        auto play=reinterpret_cast<State>(slots[5]);
        auto shutdown=reinterpret_cast<State>(slots[7]);
        std::array<RenderedLens,lens_count> lenses{{{api,player},{api,player}}};
        for(int i=0;i<lens_count;++i) lenses[i].open(win.surfaces[i],i);
        api.audio_attach(player,win.speaker);
        api.mute(player,true);
        win.gw=gw;win.live=live.get();win.player=player;
        using Completion = std::function<void(std::shared_ptr<gwbase::Error>)>;
        using SetQuality = void(*)(Live*,int,Completion);
        auto quality=reinterpret_cast<SetQuality>((*reinterpret_cast<void***>(live.get()))[5]);
        quality(live.get(),2,{});
        int rc=play(player);
        quality(live.get(),2,{});
        emit("video_play_return",rc);
        SetTimer(win.hwnd,1,400,nullptr);SetTimer(win.hwnd,2,20,nullptr);
        MSG msg{};
        while(GetMessageW(&msg,nullptr,0,0)>0){TranslateMessage(&msg);DispatchMessageW(&msg);}
        KillTimer(win.hwnd,1);KillTimer(win.hwnd,2);win.closing=true;win.stop_talk();win.speaker->enable(false);win.player=nullptr;
        if(win.recorder.events && !win.recorder.events->done){
            win.recorder.stop(gw,player);
            auto end=GetTickCount64()+4000;
            while(!win.recorder.events->done && GetTickCount64()<end)Sleep(20);
        }
        for(auto& lens:lenses)lens.close();
        shutdown(player);
        emit("video_closed");return 0;
    } catch(...) {emit("video_setup_failed");return 62;}
}
}
