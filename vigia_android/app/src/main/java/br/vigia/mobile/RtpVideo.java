package br.vigia.mobile;

import java.io.ByteArrayOutputStream;

/** Reassemble a single H.264 or H.265 RTP access unit in Annex B format. */
final class RtpVideo {
    interface Sink { void frame(byte[] bytes,long timestamp) throws Exception; }
    private static final byte[] START={0,0,0,1};
    private static final int LIMIT=6*1024*1024;
    private final boolean hevc;
    private final int payload;
    private final Sink sink;
    private final ByteArrayOutputStream frame=new ByteArrayOutputStream();
    private int next=-1;
    private long stamp=-1;
    private boolean fragmented, damaged;

    RtpVideo(boolean hevc,int payload,Sink sink){
        this.hevc=hevc;this.payload=payload;this.sink=sink;
    }
    static int u16(byte[] b,int i){return (b[i]&255)*256+(b[i+1]&255);}
    // Some cameras mark VPS/SPS/PPS as complete access units with the picture timestamp.
    static boolean containsPicture(byte[] unit,boolean hevc){
        for(int i=0;i+4<unit.length;i++){
            if(unit[i]!=0 || unit[i+1]!=0 || unit[i+2]!=0 || unit[i+3]!=1)continue;
            int type=hevc?(unit[i+4]&126)>>1:unit[i+4]&31;
            if(hevc?type<=31:(type>=1 && type<=5))return true;
        }
        return false;
    }
    private void startNal(){frame.write(START,0,4);}
    void packet(byte[] b,int size)throws Exception{
        if(size<12 || (b[0]&192)!=128 || (b[1]&127)!=payload)return;
        int p=12+4*(b[0]&15);
        if((b[0]&16)!=0){
            if(p+4>size)return;
            p+=4+4*u16(b,p+2);
        }
        if((b[0]&32)!=0)size-=b[size-1]&255;
        if(p>=size)return;
        int seq=u16(b,2);
        long time=((long)u16(b,4)<<16)|u16(b,6);
        if(next>=0 && ((seq-next)&65535)>32767)return;
        if(time!=stamp){frame.reset();fragmented=false;damaged=false;stamp=time;}
        if(next>=0 && next!=seq)damaged=true;
        next=(seq+1)&65535;
        if(!damaged && frame.size()+size*3+4<=LIMIT)damaged=!unpack(b,p,size);
        else damaged=true;
        if((b[1]&128)!=0){
            if(!damaged && !fragmented && frame.size()>0)sink.frame(frame.toByteArray(),time);
            frame.reset();fragmented=false;
        }
    }
    private boolean unpack(byte[] b,int p,int end){
        int type=hevc?(b[p]&126)>>1:b[p]&31;
        int header=hevc?2:1;
        if(end-p<header)return false;
        if(hevc?type<48:type>0 && type<24){
            if(fragmented)return false;
            startNal();frame.write(b,p,end-p);return true;
        }
        if(type==(hevc?48:24)){
            if(fragmented)return false;
            p+=header;
            while(p+2<=end){
                int length=u16(b,p);p+=2;
                if(length<header || p+length>end)return false;
                startNal();frame.write(b,p,length);p+=length;
            }
            return p==end;
        }
        if(type!=(hevc?49:28) || end-p<=header+1)return false;
        int flags=b[p+header]&255;
        if((flags&128)!=0){
            if(fragmented)return false;
            startNal();
            if(hevc){frame.write((b[p]&129)|((flags&63)<<1));frame.write(b[p+1]);}
            else frame.write((b[p]&224)|(flags&31));
            fragmented=true;
        }else if(!fragmented)return false;
        p+=header+1;
        frame.write(b,p,end-p);
        if((flags&64)!=0)fragmented=false;
        return true;
    }
}
