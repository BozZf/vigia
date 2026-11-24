package br.vigia.mobile;

/** Mono G.711 A-law carried as one sample per RTP payload byte. */
final class PcmaRtp {
    private static final short[] table=new short[256];
    static {
        for(int i=0;i<table.length;i++){
            int value=i^0x55;
            int segment=(value>>4)&7;
            int linear=((value&15)<<4)+8;
            if(segment>0)linear=(linear+256)<<(segment-1);
            table[i]=(short)((value&128)!=0?linear:-linear);
        }
    }
    short[] pcm=new short[1024];
    private int last=-1;
    int decode(byte[] bytes,int end){
        if(end<12 || end>bytes.length || (bytes[0]&192)!=128)return 0;
        int start=12+(bytes[0]&15)*4;
        if((bytes[0]&16)!=0){
            if(start+4>end)return 0;
            start+=4+4*RtpVideo.u16(bytes,start+2);
        }
        if((bytes[0]&32)!=0){
            int padding=bytes[end-1]&255;
            if(padding==0)return 0;
            end-=padding;
        }
        if(start>=end)return 0;
        int seq=RtpVideo.u16(bytes,2);
        if(last>=0 && (seq==last || ((seq-last)&65535)>=32768))return 0;
        last=seq;
        int count=end-start;
        if(pcm.length<count)pcm=new short[count];
        for(int i=0;i<count;i++)pcm[i]=table[bytes[start+i]&255];
        return count;
    }
}
