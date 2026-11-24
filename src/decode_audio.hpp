// Decode user-selected media using the codecs installed with Windows.
#include <mfapi.h>
#include <mfidl.h>
#include <mfreadwrite.h>

template<class T> struct MediaRef {
    T* ptr{};
    ~MediaRef(){if(ptr)ptr->Release();}
    T* operator->() const{return ptr;}
};
static HRESULT decode_pcm(const wchar_t* input,const wchar_t* output_path){
    MediaRef<IMFSourceReader> reader;
    HRESULT hr=MFCreateSourceReaderFromURL(input,nullptr,&reader.ptr);
    if(FAILED(hr))return hr;
    DWORD stream=MF_SOURCE_READER_FIRST_AUDIO_STREAM;
    if(FAILED(hr=reader->SetStreamSelection(MF_SOURCE_READER_ALL_STREAMS,FALSE)))return hr;
    if(FAILED(hr=reader->SetStreamSelection(stream,TRUE)))return hr;
    MediaRef<IMFMediaType> target;
    if(FAILED(hr=MFCreateMediaType(&target.ptr)))return hr;
    if(FAILED(hr=target->SetGUID(MF_MT_MAJOR_TYPE,MFMediaType_Audio)) ||
       FAILED(hr=target->SetGUID(MF_MT_SUBTYPE,MFAudioFormat_PCM)) ||
       FAILED(hr=target->SetUINT32(MF_MT_AUDIO_NUM_CHANNELS,1)) ||
       FAILED(hr=target->SetUINT32(MF_MT_AUDIO_SAMPLES_PER_SECOND,16000)) ||
       FAILED(hr=target->SetUINT32(MF_MT_AUDIO_BITS_PER_SAMPLE,16)) ||
       FAILED(hr=target->SetUINT32(MF_MT_AUDIO_BLOCK_ALIGNMENT,2)) ||
       FAILED(hr=target->SetUINT32(MF_MT_AUDIO_AVG_BYTES_PER_SECOND,32000)) ||
       FAILED(hr=reader->SetCurrentMediaType(stream,nullptr,target.ptr)))return hr;
    FILE* file=nullptr;
    if(_wfopen_s(&file,output_path,L"wb") || !file)return E_FAIL;
    uint64_t bytes=0;
    while(SUCCEEDED(hr)){
        DWORD flags=0;MediaRef<IMFSample> sample;
        hr=reader->ReadSample(stream,0,nullptr,&flags,nullptr,&sample.ptr);
        if(FAILED(hr) || (flags & MF_SOURCE_READERF_ERROR)){hr=E_FAIL;break;}
        if(sample.ptr){
            MediaRef<IMFMediaBuffer> buffer;
            if(FAILED(hr=sample->ConvertToContiguousBuffer(&buffer.ptr)))break;
            BYTE* data=nullptr;DWORD len=0;
            if(FAILED(hr=buffer->Lock(&data,nullptr,&len)))break;
            if(fwrite(data,1,len,file)!=len)hr=E_FAIL;
            buffer->Unlock();bytes+=len;
        }
        if(flags & MF_SOURCE_READERF_ENDOFSTREAM)break;
    }
    if(fclose(file) || !bytes || bytes%2)hr=E_FAIL;
    return hr;
}
static int decode_file(const wchar_t* input,const wchar_t* output_path){
    if(FAILED(CoInitializeEx(nullptr,COINIT_MULTITHREADED)))return 1;
    HRESULT hr=MFStartup(MF_VERSION);
    if(SUCCEEDED(hr)){hr=decode_pcm(input,output_path);MFShutdown();}
    CoUninitialize();return FAILED(hr)?1:0;
}
