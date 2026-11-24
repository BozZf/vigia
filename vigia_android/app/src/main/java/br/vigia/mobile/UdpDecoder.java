package br.vigia.mobile;

import android.media.*;
import android.view.Surface;
import java.io.*;
import java.nio.ByteBuffer;
import java.util.List;

/** Invoked on a single playback thread. Uses one Android decoder for the complete picture. */
final class UdpDecoder implements RtspUdp.Listener,AutoCloseable {
    interface View {
        boolean active();
        void size(int width,int height);
        void firstFrame();
    }
    private final Surface surface;
    private final View view;
    private final int width,height;
    private final byte[][] config=new byte[3][];
    private final MediaCodec.BufferInfo info=new MediaCodec.BufferInfo();
    private MediaCodec codec;
    private boolean hevc,shown;
    private long origin=-1;

    UdpDecoder(Surface surface,int width,int height,View view){
        this.surface=surface;this.width=width;this.height=height;this.view=view;
    }
    public boolean active(){return view.active();}
    public void format(boolean hevc,List<byte[]> parameters){
        this.hevc=hevc;
        for(byte[] nal:parameters)if(nal.length>0)remember(nal,0,nal.length);
    }
    private int type(byte b){return hevc?(b&126)>>1:b&31;}
    private void remember(byte[] data,int from,int to){
        int index=type(data[from])-(hevc?32:7);
        if(index<0 || index>(hevc?2:1) || to-from>65536)return;
        byte[] unit=new byte[4+to-from];unit[3]=1;
        System.arraycopy(data,from,unit,4,to-from);config[index]=unit;
    }
    private boolean prepare(byte[] frame)throws IOException{
        boolean key=false;
        for(int p=4;p<frame.length;){
            int end=p+1;
            while(end+3<frame.length && !(frame[end]==0 && frame[end+1]==0 && frame[end+2]==0 && frame[end+3]==1))end++;
            if(end+3>=frame.length)end=frame.length;
            int t=type(frame[p]);remember(frame,p,end);
            if(hevc?t>=16 && t<=23:t==5)key=true;
            p=end+4;
        }
        if(!key || config[0]==null || config[1]==null || hevc && config[2]==null)return false;
        String mime=hevc?"video/hevc":"video/avc";
        MediaFormat f=MediaFormat.createVideoFormat(mime,width,height);
        if(hevc){
            ByteArrayOutputStream all=new ByteArrayOutputStream();
            for(byte[] piece:config)all.write(piece,0,piece.length);
            f.setByteBuffer("csd-0",ByteBuffer.wrap(all.toByteArray()));
        }else{
            f.setByteBuffer("csd-0",ByteBuffer.wrap(config[0]));
            f.setByteBuffer("csd-1",ByteBuffer.wrap(config[1]));
        }
        codec=MediaCodec.createDecoderByType(mime);
        try{codec.configure(f,surface,null,0);codec.start();}
        catch(RuntimeException ex){throw new IOException("O Android não abriu o decodificador "+(hevc?"H.265":"H.264")+" para "+width+"×"+height+".");}
        return true;
    }
    public void frame(byte[] data,long stamp)throws Exception{
        if(!active() || codec==null && !prepare(data))return;
        drain();
        int input=codec.dequeueInputBuffer(20000);
        if(input>=0){
            ByteBuffer buffer=codec.getInputBuffer(input);
            if(buffer==null || buffer.capacity()<data.length)throw new IOException("Quadro maior que o buffer do decodificador.");
            buffer.clear();buffer.put(data);
            if(origin<0)origin=stamp;
            codec.queueInputBuffer(input,0,data.length,((stamp-origin)&0xffffffffL)*1000/90,0);
        }
        drain();
    }
    private void drain(){
        while(active()){
            int out=codec.dequeueOutputBuffer(info,0);
            if(out==MediaCodec.INFO_OUTPUT_FORMAT_CHANGED){
                MediaFormat f=codec.getOutputFormat();
                int w=f.getInteger("width"),h=f.getInteger("height");
                if(f.containsKey("crop-right") && f.containsKey("crop-left"))w=f.getInteger("crop-right")-f.getInteger("crop-left")+1;
                if(f.containsKey("crop-bottom") && f.containsKey("crop-top"))h=f.getInteger("crop-bottom")-f.getInteger("crop-top")+1;
                view.size(w,h);
            }else if(out>=0){
                boolean render=info.size>0;
                codec.releaseOutputBuffer(out,render);
                if(render && !shown){shown=true;view.firstFrame();}
            }else return;
        }
    }
    public void close(){if(codec!=null){try{codec.release();}finally{codec=null;}}}
}
