// Windows x64, Yoosee 1.0.0.14. Included inside namespace preview.
struct OutputConfig { float volume; double rate; int channels,bits,hz; };
static_assert(offsetof(OutputConfig,hz)==24);
inline WAVEFORMATEX pcm_format(int channels,int bits,int hz) {
    WAVEFORMATEX f{};
    f.wFormatTag=WAVE_FORMAT_PCM; f.nChannels=static_cast<WORD>(channels);
    f.wBitsPerSample=static_cast<WORD>(bits); f.nSamplesPerSec=hz;
    f.nBlockAlign=static_cast<WORD>(channels*bits/8); f.nAvgBytesPerSec=hz*f.nBlockAlign;
    return f;
}
// AbstractAudioRenderer vtable from GWPlayerLibV1. Buffers stay at stable
// addresses until WinMM returns ownership. Only open the speaker on user request.
class Speaker {
    struct Block { WAVEHDR hdr{}; std::vector<char> pcm; };
    std::mutex lock_;
    std::array<Block,12> blocks_{};
    WAVEFORMATEX format_{};
    HWAVEOUT device_{};
    bool enabled_=false, attempted_=false, announced_=false;
    void close_device() {
        if(device_){
            waveOutReset(device_);
            for(auto& b:blocks_) if(b.hdr.dwFlags & WHDR_PREPARED){
                waveOutUnprepareHeader(device_,&b.hdr,sizeof b.hdr); b.hdr={};
            }
            waveOutClose(device_); device_=nullptr;
        }
        attempted_=announced_=false;
    }
public:
    virtual ~Speaker(){close_device();}
    virtual void init(const OutputConfig& cfg){
        std::lock_guard<std::mutex> guard(lock_);
        close_device(); format_={};
        if(cfg.channels>=1 && cfg.channels<=8 && (cfg.bits==8||cfg.bits==16||cfg.bits==24||cfg.bits==32)
            && cfg.hz>=8000 && cfg.hz<=192000) format_=pcm_format(cfg.channels,cfg.bits,cfg.hz);
    }
    virtual void set_channel_id(int){}
    virtual void frameUpdate(const unsigned char* data,int len){
        std::lock_guard<std::mutex> guard(lock_);
        if(!enabled_ || !format_.nBlockAlign || !data || len<=0 || len>1048576)return;
        if(!device_ && !attempted_){
            attempted_=true;
            auto rc=waveOutOpen(&device_,WAVE_MAPPER,&format_,0,0,CALLBACK_NULL);
            emit("audio_output_open",static_cast<int>(rc));
            if(rc!=MMSYSERR_NOERROR){device_=nullptr;return;}
        }
        if(!device_)return;
        for(auto& b:blocks_){
            if(b.hdr.dwFlags & WHDR_INQUEUE)continue;
            if(b.hdr.dwFlags & WHDR_PREPARED)
                if(waveOutUnprepareHeader(device_,&b.hdr,sizeof b.hdr))continue;
            b.pcm.assign(data,data+len); b.hdr={}; b.hdr.lpData=b.pcm.data(); b.hdr.dwBufferLength=len;
            auto rc=waveOutPrepareHeader(device_,&b.hdr,sizeof b.hdr);
            if(!rc)rc=waveOutWrite(device_,&b.hdr,sizeof b.hdr);
            if(!announced_){emit("audio_output_write",static_cast<int>(rc));announced_=true;}
            break;
        }
    }
    virtual void release(){std::lock_guard<std::mutex> guard(lock_);close_device();}
    virtual int setVolume(float){return 0;}
    virtual void setRenderState(int){}
    virtual int64_t computeRenderPosition(int64_t pts,double timebase,float){return static_cast<int64_t>(pts*timebase);}
    void enable(bool value){
        std::lock_guard<std::mutex> guard(lock_);
        enabled_=value; if(!value)close_device();
    }
};
#pragma pack(push,1)
struct TalkFormat { uint8_t codec=5; int options=0,channels=1,bits=16,hz=16000,samples=320; };
#pragma pack(pop)
static_assert(sizeof(TalkFormat)==21);
struct alignas(8) FrameHolder { unsigned char data[312]; };
struct FrameListener { virtual int receive(FrameHolder&)=0; };

// Helpers belong to the SHA-256-pinned GWPlayerLibV1. Their constructors
// preserve the SDK reference count when its encoder queues or retains a frame.
struct FrameApi {
    using NewFrame=unsigned char*(*)();
    using FreeFrame=void(*)(unsigned char**);
    using Buffer=int(*)(unsigned char*,int);
    using Unary=void(*)(void*);
    using Wrap=void(*)(void*,void*,void*,unsigned char,unsigned char);
    NewFrame alloc; FreeFrame free_frame; Buffer get_buffer; Unary metadata,drop; Wrap wrap;
    FrameApi(HMODULE gw){
        auto av=GetModuleHandleW(L"avutil-56.dll");
        alloc=symbol<NewFrame>(av,"av_frame_alloc");free_frame=symbol<FreeFrame>(av,"av_frame_free");
        get_buffer=symbol<Buffer>(av,"av_frame_get_buffer");
        auto base=reinterpret_cast<unsigned char*>(gw);
        metadata=reinterpret_cast<Unary>(base+0x463c0);
        wrap=reinterpret_cast<Wrap>(base+0x44fa0);
        drop=reinterpret_cast<Unary>(base+0x47160);
    }
    template<class T> static void field(unsigned char* frame,size_t offset,T value){std::memcpy(frame+offset,&value,sizeof value);}
    int deliver(FrameListener& sink,const char* pcm,int length) {
        if(length!=640)return -1;
        auto frame=alloc(); if(!frame)return -1;
        // avutil-56 AVFrame layout from the matching PDB.
        field(frame,112,320); field(frame,116,1); field(frame,272,16000);
        field(frame,280,uint64_t{4}); field(frame,444,1);
        if(get_buffer(frame,1)<0){free_frame(&frame);return -1;}
        auto now=std::chrono::system_clock::now().time_since_epoch();
        field(frame,136,std::chrono::duration_cast<std::chrono::microseconds>(now).count());
        field(frame,424,int64_t{20000}); field(frame,64,length);
        std::memcpy(*reinterpret_cast<unsigned char**>(frame),pcm,length);
        alignas(8) unsigned char info[288]{}; FrameHolder holder{};
        metadata(info);
        // The by-value metadata temporary is destroyed by the constructor.
        wrap(&holder,frame,info,0,0);
        try {int rc=sink.receive(holder);drop(&holder);return rc;}
        catch(...){drop(&holder);throw;}
    }
};
struct CaptureInterface {
    virtual const TalkFormat& get_audio_format()=0;
    virtual void set_audio_format(const TalkFormat&)=0;
    virtual void set_listener(std::weak_ptr<FrameListener>)=0;
    virtual void set_channel_id(int)=0;
    virtual int start()=0;
    virtual int stop()=0;
    virtual bool is_capturing()=0;
};
class Microphone final : public CaptureInterface {
    // IAudioCapture has seven virtual methods and no virtual destructor.
    std::deque<TalkFormat> formats_{TalkFormat{}};
    std::atomic<const TalkFormat*> current_{&formats_.front()};
    std::mutex lock_;
    std::weak_ptr<FrameListener> listener_;
    std::atomic<bool> compatible_{true}, requested_{false}, cancelled_{false};
    HWAVEIN input_{};
    struct Block { WAVEHDR hdr{}; std::array<char,640> pcm{}; };
    std::array<Block,8> blocks_{};
    unsigned next_=0;
    FrameApi frames_;
    TalkBurst burst_;
    FILE* clip_=nullptr;
    ULONGLONG due_=0;
    bool clip_started_=false;
    bool clip_tick(){
        if(!clip_started_){clip_started_=true;due_=GetTickCount64();emit("alert_audio_started");}
        auto now=GetTickCount64();
        if(now>due_+80)due_=now;
        for(int i=0;i<4 && due_<=now;++i,due_+=20){
            std::shared_ptr<FrameListener> sink;
            {std::lock_guard<std::mutex> g(lock_);sink=listener_.lock();}
            if(!sink)continue;
            std::array<char,640> pcm{};
            if(!read_looped_pcm(clip_,pcm.data(),pcm.size()))return false;
            auto rc=frames_.deliver(*sink,pcm.data(),640);
            if(rc<0 && rc!=-2){emit("mic_frame_error",rc);return false;}
        }
        return true;
    }
    const wchar_t* status_=L"Interfone encerrado";
public:
    explicit Microphone(HMODULE gw,bool alert):frames_(gw){
        if(alert){
            wchar_t path[32768]{};auto size=GetEnvironmentVariableW(L"YOOSEE_ALERT_PATH",path,32768);
            if(!size || size>=32768 || _wfopen_s(&clip_,path,L"rb") || !clip_)throw std::runtime_error("audio file");
        }
    }
    const TalkFormat& get_audio_format() override {return *current_.load();}
    void set_audio_format(const TalkFormat& f) override {
        std::lock_guard<std::mutex> g(lock_);
        if(std::memcmp(current_.load(),&f,sizeof f)!=0){
            formats_.push_back(f);current_.store(&formats_.back());
        }
        compatible_=(f.channels==1 && f.bits==16 && f.hz==16000);
        if(!compatible_)emit("mic_format_unsupported",f.hz);
    }
    void set_listener(std::weak_ptr<FrameListener> w) override {std::lock_guard<std::mutex> g(lock_);listener_=std::move(w);}
    void set_channel_id(int) override {}
    int start() override {if(cancelled_ || !compatible_)return -1;requested_=true;return 0;}
    int stop() override {if(requested_)cancelled_=true;return 0;}
    bool is_capturing() override {return requested_ && !cancelled_;}
    bool started() const{return input_!=nullptr || clip_started_;}
    unsigned seconds_left() const{return burst_.seconds_left(GetTickCount64());}
    const wchar_t* stop_message() const{return status_;}
    // All WinMM handle operations run on the preview thread. SDK callbacks only
    // update flags and the listener. No callback touches the preview window.
    bool tick(){
        if(!compatible_){status_=L"Formato de voz incompatível";return false;}
        if(cancelled_)return false;
        if(!requested_)return true;
        if(clip_)return clip_tick();
        if(!input_){
            auto f=pcm_format(1,16,16000);
            auto rc=waveInOpen(&input_,WAVE_MAPPER,&f,0,0,CALLBACK_NULL);
            emit("mic_open",static_cast<int>(rc));
            if(rc){input_=nullptr;status_=L"Falha ao abrir microfone";return false;}
            for(auto& b:blocks_){
                b.hdr.lpData=b.pcm.data();b.hdr.dwBufferLength=static_cast<DWORD>(b.pcm.size());
                rc=waveInPrepareHeader(input_,&b.hdr,sizeof b.hdr);
                if(!rc)rc=waveInAddBuffer(input_,&b.hdr,sizeof b.hdr);
                if(rc){emit("mic_error",static_cast<int>(rc));status_=L"Falha na captura de voz";return false;}
            }
            rc=waveInStart(input_);if(rc){emit("mic_error",static_cast<int>(rc));status_=L"Falha na captura de voz";return false;}
            burst_.start(GetTickCount64());emit("mic_started");
        }
        for(size_t i=0;i<blocks_.size();++i){
            if(cancelled_ || !seconds_left()){
                if(!burst_.blocks())status_=L"Sem blocos de áudio";
                return false;
            }
            if(!burst_.wants_block())break;
            auto& b=blocks_[next_]; if(!(b.hdr.dwFlags & WHDR_DONE))break;
            std::shared_ptr<FrameListener> sink;
            {std::lock_guard<std::mutex> g(lock_);sink=listener_.lock();}
            if(sink && b.hdr.dwBytesRecorded==b.pcm.size()){
                auto rc=frames_.deliver(*sink,b.pcm.data(),static_cast<int>(b.pcm.size()));
                if(!burst_.submitted(rc)){
                    emit("mic_frame_error",rc);status_=L"Falha no envio de voz";return false;
                }
                if(burst_.blocks()==1)emit("mic_first_frame",rc);
            }
            b.hdr.dwBytesRecorded=0;
            auto rc=waveInAddBuffer(input_,&b.hdr,sizeof b.hdr);
            if(rc){emit("mic_error",static_cast<int>(rc));status_=L"Falha na captura de voz";return false;}
            next_=(next_+1)%static_cast<unsigned>(blocks_.size());
        }
        return true;
    }
    void close(){
        cancelled_=true;
        if(clip_){fclose(clip_);clip_=nullptr;}
        if(!input_)return;
        if(burst_.started())emit("mic_capture_ms",static_cast<int>(std::min<uint64_t>(burst_.elapsed_ms(GetTickCount64()),INT_MAX)));
        waveInReset(input_);
        for(auto& b:blocks_)if(b.hdr.dwFlags & WHDR_PREPARED)waveInUnprepareHeader(input_,&b.hdr,sizeof b.hdr);
        waveInClose(input_);input_=nullptr;
        emit("mic_frames",static_cast<int>(burst_.blocks()));
        emit("mic_encoder_drained",static_cast<int>(burst_.drained()));
    }
    ~Microphone(){close();}
};
struct alignas(8) TalkStorage{unsigned char data[168];};
using Completion=std::function<void(std::shared_ptr<gwbase::Error>)>;
struct Talk {
    void* live;
    std::shared_ptr<Microphone> mic;
    std::shared_ptr<void> iface;
    std::shared_ptr<std::atomic<bool>> failed=std::make_shared<std::atomic<bool>>(false);
    ULONGLONG setup_deadline=0;
    bool linked=false;
    using Set=void(*)(void*,std::shared_ptr<void>);
    using Command=int(*)(void*,Completion);
    Talk(HMODULE sdk,HMODULE gw,void* l,std::shared_ptr<void> connection,bool alert=false):live(l),mic(std::make_shared<Microphone>(gw,alert)){
        if(!connection)throw std::runtime_error("no connection");
        using Init=void(*)(void*,std::shared_ptr<CaptureInterface>,std::shared_ptr<void>,int);
        auto init=symbol<Init>(sdk,"??0Intercom@iotvideo@@QEAA@V?$shared_ptr@VIAudioCapture@gwplayer@@@std@@V?$shared_ptr@VConnection@iotvideo@@@3@@Z");
        auto destroy=symbol<void(*)(void*)>(sdk,"??1Intercom@iotvideo@@QEAA@XZ");
        auto storage=std::make_unique<TalkStorage>();auto ptr=storage.get();
        init(ptr,mic,std::move(connection),1);
        std::shared_ptr<TalkStorage> owner(storage.release(),[destroy](TalkStorage* p){destroy(p);::operator delete(p);});
        auto offset=(*reinterpret_cast<const int32_t**>(ptr))[1];
        if(offset!=160)throw std::runtime_error("intercom interface");
        iface={owner,ptr->data+offset};
    }
    void** slots(){return *reinterpret_cast<void***>(iface.get());}
    bool begin(){
        using Config=void(*)(void*,std::function<void(TalkFormat&)>);
        reinterpret_cast<Config>(slots()[1])(iface.get(),[](TalkFormat& f){f=TalkFormat{};});
        reinterpret_cast<Set>((*reinterpret_cast<void***>(live))[0])(live,iface);linked=true;
        setup_deadline=GetTickCount64()+10000;
        int rc=reinterpret_cast<Command>(slots()[3])(iface.get(),[flag=failed,keep=iface](std::shared_ptr<gwbase::Error> err){
            if(err && err->code)flag->store(true);
            emit("talk_start_reply",err?err->code:0);
        });
        emit("talk_start_result",rc);return rc==0;
    }
    bool tick(){
        if(failed->load())return false;
        if(!mic->started() && GetTickCount64()>=setup_deadline){emit("talk_setup_timeout");return false;}
        return mic->tick();
    }
    const wchar_t* stop_message() const{
        if(failed->load())return L"Interfone recusado";
        if(!mic->started() && GetTickCount64()>=setup_deadline)return L"Interfone sem resposta";
        return mic->stop_message();
    }
    ~Talk(){
        mic->close();
        if(linked){
            auto rc=reinterpret_cast<Command>(slots()[6])(iface.get(),[keep=iface](std::shared_ptr<gwbase::Error> e){emit("talk_end_reply",e?e->code:0);});
            emit("talk_end_result",rc);
            // The vendor keeps its intercom attached until the next session or player shutdown.
        }
    }
};
