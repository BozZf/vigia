package br.vigia.mobile;

import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioTrack;
import java.io.IOException;
import java.util.function.BooleanSupplier;

/** All output operations run on the listening worker. */
final class CameraSpeaker implements RtspUdp.AudioListener,AutoCloseable {
    private final BooleanSupplier enabled;
    private final Runnable onPlaying;
    private AudioTrack output;
    private boolean playing;
    CameraSpeaker(BooleanSupplier enabled,Runnable onPlaying){
        this.enabled=enabled;this.onPlaying=onPlaying;
    }
    public boolean active(){return enabled.getAsBoolean();}
    public void format(int rate)throws IOException{
        if(!active())return;
        int channel=AudioFormat.CHANNEL_OUT_MONO,encoding=AudioFormat.ENCODING_PCM_16BIT;
        int min=AudioTrack.getMinBufferSize(rate,channel,encoding);
        if(min<=0)throw new IOException("O celular não aceitou a taxa de áudio.");
        output=new AudioTrack(AudioManager.STREAM_MUSIC,rate,channel,encoding,
            Math.max(min,rate/5),AudioTrack.MODE_STREAM);
        if(output.getState()!=AudioTrack.STATE_INITIALIZED)throw new IOException("A saída de som não abriu.");
        output.play();
    }
    public void samples(short[] data,int count)throws IOException{
        int offset=0;
        while(active() && offset<count){
            int n=output.write(data,offset,Math.min(512,count-offset));
            if(n<=0)throw new IOException("A saída de som foi interrompida.");
            offset+=n;
            if(!playing){playing=true;onPlaying.run();}
        }
    }
    public void close(){
        if(output!=null){
            try{if(output.getState()==AudioTrack.STATE_INITIALIZED){output.pause();output.flush();}}
            finally{output.release();output=null;}
        }
    }
}
