package br.vigia.mobile;

import java.util.*;

public class RtpVideoTest {
    static byte[] packet(int seq,int time,boolean mark,int...body){
        byte[] b=new byte[12+body.length];b[0]=(byte)128;b[1]=(byte)(96+(mark?128:0));b[3]=(byte)seq;b[7]=(byte)time;
        for(int i=0;i<body.length;i++)b[12+i]=(byte)body[i];return b;
    }
    static void feed(RtpVideo r,byte[] b)throws Exception{r.packet(b,b.length);}
    public static void main(String[] args)throws Exception{
        List<byte[]> out=new ArrayList<>();
        for(boolean hevc:new boolean[]{false,true}){
            out.clear();RtpVideo parser=new RtpVideo(hevc,96,(bytes,ts)->out.add(bytes));
            int[] start=hevc?new int[]{98,1,147,5}:new int[]{124,133,5};
            int[] end=hevc?new int[]{98,1,83,7}:new int[]{124,69,7};
            feed(parser,packet(1,1,false,start));feed(parser,packet(2,1,true,end));
            byte[] expected=hevc?new byte[]{0,0,0,1,38,1,5,7}:new byte[]{0,0,0,1,101,5,7};
            if(out.size()!=1 || !Arrays.equals(out.get(0),expected))throw new AssertionError();
            feed(parser,packet(3,2,false,start));feed(parser,packet(5,2,true,end));
            if(out.size()!=1)throw new AssertionError("incomplete fragment");
            feed(parser,packet(6,3,true,hevc?new int[]{96,1,0,2,38,1}:new int[]{24,0,2,101,9}));
            if(out.size()!=2)throw new AssertionError("aggregation");
        }
        if(RtpVideo.containsPicture(new byte[]{0,0,0,1,64,1},true) ||
                RtpVideo.containsPicture(new byte[]{0,0,0,1,103,5},false) ||
                !RtpVideo.containsPicture(new byte[]{0,0,0,1,66,1,0,0,0,1,38,1},true))
            throw new AssertionError("configuration-only samples must not create pictures");
        String sdp="v=0\r\na=control:*\r\nm=audio 0 RTP/AVP 8\r\na=control:track1\r\nm=video 0 RTP/AVP 97\r\na=rtpmap:97 H265/90000\r\na=control:track2\r\n";
        RtspUdp.Track t=RtspUdp.Track.parse(sdp);
        if(!t.hevc || t.payload!=97 || !"track2".equals(t.path))throw new AssertionError();
        RtspUdp.Track audio=RtspUdp.Track.audio("v=0\r\nm=audio 0 RTP/AVP 97\r\na=rtpmap:97 PCMA/16000/1\r\na=control:track1\r\n");
        if(audio.sampleRate!=16000 || audio.payload!=97)throw new AssertionError("PCMA profile");
        PcmaRtp pcma=new PcmaRtp();
        byte[] samples=packet(1,1,true,0xd5,0x55,0xaa,0x2a);
        if(pcma.decode(samples,samples.length)!=4 || pcma.pcm[0]!=8 || pcma.pcm[1]!=-8 ||
            pcma.pcm[2]!=32256 || pcma.pcm[3]!=-32256 || pcma.decode(samples,samples.length)!=0)
            throw new AssertionError("A-law PCM or repeated packet");
        System.out.println("OK: video track, H264/H265 fragmentation, aggregation, packet loss.");
    }
}
