package br.vigia.mobile;

import java.nio.ShortBuffer;
import java.util.ArrayDeque;
import java.util.Arrays;

/** A short PCM window shared by the RTP receiver and the MP4 writer. Times use the
 * monotonic clock only to align the first packet; later timestamps use the camera clock. */
final class ClipSound {
    private static final class Packet {
        final long startUs;
        final short[] data;
        Packet(long startUs, short[] data) { this.startUs=startUs; this.data=data; }
    }
    final long requestedUs = nowUs();
    private final ArrayDeque<Packet> packets = new ArrayDeque<>();
    private int rate;
    private long anchorUs, lastStamp, ticks;
    private boolean anchored;
    private volatile boolean unavailable;

    static long nowUs() { return System.nanoTime()/1000; }
    void failed() { unavailable=true; }
    synchronized int rate() { return rate; }
    synchronized boolean waiting() {
        return rate==0 && !unavailable && nowUs()-requestedUs < 2_000_000;
    }

    synchronized void offer(short[] pcm,int count,int hz,long stamp,long arrivalUs){
        if(count<=0 || hz<=0 || (rate!=0 && rate!=hz))return;
        rate=hz;
        if(!anchored){
            anchorUs=arrivalUs-count*1_000_000L/hz;
            anchored=true;
        } else {
            ticks+=(int)(stamp-lastStamp);
        }
        lastStamp=stamp;
        long start=anchorUs+ticks*1_000_000L/hz;
        packets.addLast(new Packet(start,Arrays.copyOf(pcm,count)));
        while(packets.size()>512 || start-packets.peekFirst().startUs>3_000_000)
            packets.removeFirst();
    }

    /** Copies an exact time interval. A lost packet leaves silence in its own slot. */
    synchronized void read(ShortBuffer dest,int count,long originUs,long firstSample){
        long position=firstSample;
        while(count>0){
            Packet packet=packets.peekFirst();
            if(packet==null){while(count-->0)dest.put((short)0);return;}
            long start=Math.round((packet.startUs-originUs)*(double)rate/1_000_000);
            long offset=position-start;
            if(offset>=packet.data.length){packets.removeFirst();continue;}
            int n;
            if(offset<0){
                n=(int)Math.min(count,-offset);
                for(int i=0;i<n;i++)dest.put((short)0);
            } else {
                n=Math.min(count,packet.data.length-(int)offset);
                dest.put(packet.data,(int)offset,n);
            }
            count-=n;position+=n;
        }
    }
}
