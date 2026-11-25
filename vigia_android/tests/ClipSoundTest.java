package br.vigia.mobile;

import java.nio.ShortBuffer;
import java.util.Arrays;

public final class ClipSoundTest {
    private static final int HZ=16000;
    private static final long ORIGIN=5_000_000;

    private static short[] tone(int value){
        short[] pcm=new short[320];Arrays.fill(pcm,(short)value);return pcm;
    }
    private static void range(short[] data,int from,int to,int expected){
        for(int i=from;i<to;i++)if(data[i]!=expected)throw new AssertionError("sample "+i);
    }
    public static void main(String[] args){
        ClipSound clip=new ClipSound();
        short[] first=tone(1);
        clip.offer(first,320,HZ,0xffffff00L,ORIGIN+20_000);
        Arrays.fill(first,(short)88); // Network receiver reuses its array.
        clip.offer(tone(2),320,HZ,64,ORIGIN+41_000); // RTP wrap and network jitter.
        clip.offer(tone(4),320,HZ,704,ORIGIN+83_000); // Third packet lost.
        ShortBuffer out=ShortBuffer.allocate(1440);
        clip.read(out,480,ORIGIN+10_000,0);
        clip.read(out,960,ORIGIN+10_000,480);
        range(out.array(),0,160,1);
        range(out.array(),160,480,2);
        range(out.array(),480,800,0);
        range(out.array(),800,1120,4);
        range(out.array(),1120,1440,0);

        ClipSound late=new ClipSound();
        late.offer(tone(7),320,HZ,300,ORIGIN+40_000);
        ShortBuffer aligned=ShortBuffer.allocate(640);
        late.read(aligned,640,ORIGIN,0);
        range(aligned.array(),0,320,0);
        range(aligned.array(),320,640,7);
        ClipSound burst=new ClipSound();
        burst.offer(tone(1),320,HZ,0,ORIGIN+20_000);
        if(burst.readyUntil(ORIGIN,1_400_000)!=20_000)throw new AssertionError("encoded missing audio early");
        for(int i=1;i<70;i++)burst.offer(tone(2),320,HZ,i*320,ORIGIN+1_410_000);
        if(burst.readyUntil(ORIGIN,1_400_000)!=1_400_000)throw new AssertionError("late burst lost");
        if(burst.readyUntil(ORIGIN,4_000_000)!=2_400_000)throw new AssertionError("unbounded wait");
        ClipSound unavailable=new ClipSound();
        unavailable.failed();
        if(unavailable.waiting() || unavailable.rate()!=0)throw new AssertionError();
        System.out.println("OK: PCM alignment, gaps, RTP wrap, receiver buffer reuse and video-only fallback readiness.");
    }
}
