package br.vigia.mobile;

import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaFormat;
import android.media.MediaMuxer;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

/** Encoder and muxer calls are serialized on the video worker. */
final class ClipAac implements AutoCloseable {
    private static final int[] RATES={96000,88200,64000,48000,44100,32000,24000,22050,16000,12000,11025,8000,7350};
    private final ClipSound sound;
    private final MediaMuxer muxer;
    private final MediaCodec.BufferInfo info=new MediaCodec.BufferInfo();
    private final long originUs;
    private final int rate;
    private MediaCodec encoder;
    private int track;
    private long written, lastPts=-1;
    private boolean ended;

    ClipAac(ClipSound sound, MediaMuxer muxer, long originUs) throws IOException {
        this.sound=sound; this.muxer=muxer; this.originUs=originUs; rate=sound.rate();
        int index=0;
        while(index<RATES.length && RATES[index]!=rate)index++;
        if(index==RATES.length)throw new IOException("Taxa de áudio incompatível.");
        String mime="audio/mp4a-latm";
        MediaFormat format=MediaFormat.createAudioFormat(mime,rate,1);
        format.setInteger(MediaFormat.KEY_AAC_PROFILE,MediaCodecInfo.CodecProfileLevel.AACObjectLC);
        format.setInteger(MediaFormat.KEY_BIT_RATE,rate<=16000?32000:64000);
        encoder=MediaCodec.createEncoderByType(mime);
        try {
            encoder.configure(format,null,null,MediaCodec.CONFIGURE_FLAG_ENCODE);
            encoder.start();
            // ISO/IEC 14496-3 AudioSpecificConfig: AAC-LC, indexed frequency, mono.
            int config=(2<<11)|(index<<7)|(1<<3);
            format.setByteBuffer("csd-0",ByteBuffer.wrap(new byte[]{(byte)(config>>8),(byte)config}));
            track=muxer.addTrack(format);
        } catch(RuntimeException e){close();throw e;}
    }

    void writeAvailable(long videoUs) throws IOException {
        writeUntil(sound.readyUntil(originUs,videoUs));
    }

    private void writeUntil(long timeUs) throws IOException {
        long end=Math.max(0,timeUs)*rate/1_000_000;
        while(written<end){
            int input=input();
            ByteBuffer bytes=encoder.getInputBuffer(input);
            if(bytes==null || bytes.capacity()<2)throw new IOException("Buffer AAC indisponível.");
            bytes.clear(); bytes.order(ByteOrder.nativeOrder());
            int count=(int)Math.min(Math.min(1024,bytes.remaining()/2),end-written);
            sound.read(bytes.asShortBuffer(),count,originUs,written);
            encoder.queueInputBuffer(input,0,count*2,written*1_000_000L/rate,0);
            written+=count;
            drain(0);
        }
    }

    private int input() throws IOException {
        for(int i=0;i<100;i++){
            int index=encoder.dequeueInputBuffer(10000);
            if(index>=0)return index;
            drain(0);
        }
        throw new IOException("Tempo esgotado ao codificar áudio.");
    }

    private void drain(long firstWaitUs){
        for(;;){
            int index=encoder.dequeueOutputBuffer(info,firstWaitUs);
            firstWaitUs=0;
            if(index==MediaCodec.INFO_OUTPUT_FORMAT_CHANGED || index==MediaCodec.INFO_OUTPUT_BUFFERS_CHANGED)continue;
            if(index<0)return;
            try {
                if(info.size>0 && (info.flags & MediaCodec.BUFFER_FLAG_CODEC_CONFIG)==0){
                    ByteBuffer encoded=encoder.getOutputBuffer(index);
                    if(encoded==null)throw new IllegalStateException("AAC sem dados.");
                    info.presentationTimeUs=Math.max(lastPts+1,info.presentationTimeUs);
                    muxer.writeSampleData(track,encoded,info);
                    lastPts=info.presentationTimeUs;
                }
                ended=(info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM)!=0;
            } finally { encoder.releaseOutputBuffer(index,false); }
            if(ended)return;
        }
    }

    void finish(long durationUs) throws IOException {
        writeUntil(Math.max(1_024_000_000L/rate,durationUs));
        encoder.queueInputBuffer(input(),0,0,written*1_000_000L/rate,MediaCodec.BUFFER_FLAG_END_OF_STREAM);
        for(int i=0;!ended && i<100;i++)drain(10000);
        if(!ended || lastPts<0)throw new IOException("O áudio não foi finalizado.");
    }

    public void close(){if(encoder!=null){try{encoder.release();}finally{encoder=null;}}}
}
