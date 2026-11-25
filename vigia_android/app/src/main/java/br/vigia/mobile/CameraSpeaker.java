package br.vigia.mobile;

import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioTrack;
import java.io.IOException;
import java.util.function.BooleanSupplier;
import java.util.function.Supplier;

/** All output operations run on the listening worker. */
final class CameraSpeaker implements RtspUdp.AudioListener,AutoCloseable {
    private final BooleanSupplier enabled;
    private final BooleanSupplier monitor;
    private final Supplier<ClipSound> clip;
    private final Runnable onPlaying, onSpeakerError;
    private AudioTrack output;
    private int rate;
    private boolean playing;
    CameraSpeaker(BooleanSupplier enabled,BooleanSupplier monitor,Supplier<ClipSound> clip,
                  Runnable onPlaying,Runnable onSpeakerError){
        this.enabled=enabled;this.monitor=monitor;this.clip=clip;
        this.onPlaying=onPlaying;this.onSpeakerError=onSpeakerError;
    }
    public boolean active(){return enabled.getAsBoolean();}
    public void format(int rate){this.rate=rate;}
    private void openSpeaker() throws IOException {
        int channel=AudioFormat.CHANNEL_OUT_MONO,encoding=AudioFormat.ENCODING_PCM_16BIT;
        int min=AudioTrack.getMinBufferSize(rate,channel,encoding);
        if(min<=0)throw new IOException("O celular não aceitou a taxa de áudio.");
        output=new AudioTrack(AudioManager.STREAM_MUSIC,rate,channel,encoding,
            Math.max(min,rate/5),AudioTrack.MODE_STREAM);
        if(output.getState()!=AudioTrack.STATE_INITIALIZED)throw new IOException("A saída de som não abriu.");
        output.play();
    }
    @Override public void packetSamples(short[] data,int count,long stamp){
        if(!active())return;
        ClipSound recorder=clip.get();
        if(recorder!=null)recorder.offer(data,count,rate,stamp,ClipSound.nowUs());
        if(!monitor.getAsBoolean()){close();return;}
        try{
            if(output==null)openSpeaker();
            samples(data,count);
        }catch(IOException | RuntimeException e){close();onSpeakerError.run();}
    }
    public void samples(short[] data,int count)throws IOException{
        int offset=0;
        while(active() && monitor.getAsBoolean() && offset<count){
            int n=output.write(data,offset,Math.min(512,count-offset));
            if(n<=0)throw new IOException("A saída de som foi interrompida.");
            offset+=n;
            if(!playing){playing=true;onPlaying.run();}
        }
    }
    public void close(){
        if(output!=null){
            try{if(output.getState()==AudioTrack.STATE_INITIALIZED){output.pause();output.flush();}}
            finally{output.release();output=null;playing=false;}
        }
    }
}
