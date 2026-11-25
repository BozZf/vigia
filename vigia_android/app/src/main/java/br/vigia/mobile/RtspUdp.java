package br.vigia.mobile;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.regex.*;

/** One RTSP control connection and one unicast UDP media track. */
final class RtspUdp {
    interface Listener {
        boolean active();
        void format(boolean hevc,List<byte[]> parameters)throws Exception;
        void frame(byte[] data,long timestamp)throws Exception;
    }
    interface AudioListener {
        boolean active();
        void format(int sampleRate)throws Exception;
        void samples(short[] pcm,int count)throws Exception;
        default void packetSamples(short[] pcm,int count,long stamp)throws Exception { samples(pcm,count); }
    }
    private interface Receiver {
        boolean active();
        Track select(String sdp)throws Exception;
        void packet(byte[] data,int length)throws Exception;
    }
    private final URI url;
    private final String[] login;
    private int sequence;
    private String session="",challenge="";
    private Socket control;
    private int keepAliveSeconds=20;
    RtspUdp(URI input){
        url=DiagnosticoRtsp.enderecoSemUsuario(input);
        login=input.getRawUserInfo()==null?new String[0]:input.getRawUserInfo().split(":",2);
    }
    private DiagnosticoRtsp.Reply request(String method,URI target,String headers)throws Exception{
        for(int i=0;i<2;i++){
            String auth="";
            if(!challenge.isEmpty() && login.length==2){
                String u=URLDecoder.decode(login[0],"UTF-8"),p=URLDecoder.decode(login[1],"UTF-8");
                String token=CameraOnvif.digestHeader(challenge,method,target.toASCIIString(),u,p);
                if(token==null && challenge.regionMatches(true,0,"Basic ",0,6))
                    token="Basic "+Base64.getEncoder().encodeToString((u+":"+p).getBytes(StandardCharsets.UTF_8));
                if(token!=null)auth="Authorization: "+token+"\r\n";
            }
            String msg=method+" "+target.toASCIIString()+" RTSP/1.0\r\nCSeq: "+(++sequence)+"\r\nUser-Agent: Vigia/0.3.0\r\n"+
                (session.isEmpty()?"":"Session: "+session+"\r\n")+headers+auth+"\r\n";
            control.getOutputStream().write(msg.getBytes(StandardCharsets.UTF_8));
            DiagnosticoRtsp.Reply r=DiagnosticoRtsp.read(control.getInputStream());
            if(i==0 && r.status==401 && !r.challenge.isEmpty() && login.length==2){
                challenge=r.challenge;
                if(r.close){control.close();connect();}
                continue;
            }
            if(r.status!=200)throw new IOException(method+" · RTSP "+r.status+".");
            return r;
        }
        throw new IOException("Autenticação RTSP recusada.");
    }
    private void connect()throws IOException{
        control=new Socket(Proxy.NO_PROXY);
        control.connect(new InetSocketAddress(url.getHost(),url.getPort()<0?554:url.getPort()),3000);
        control.setSoTimeout(3000);
    }
    static final class Track {
        int payload;
        boolean hevc;
        String path="", aggregate="";
        final List<byte[]> parameters=new ArrayList<>();
        static Track parse(String sdp)throws IOException{
            String[] media=sdp.replace("\r","").split("(?m)^m=");
            String agg=attribute(media[0],"control");
            for(int i=1;i<media.length;i++){
                String block=media[i];
                String[] desc=block.split("\n",2)[0].trim().split("\\s+");
                if(desc.length<4 || !desc[0].equals("video"))continue;
                for(int j=3;j<desc.length;j++){
                    if(!desc[j].matches("[0-9]{1,3}"))continue;
                    String id=desc[j];
                    Matcher m=Pattern.compile("(?im)^a=rtpmap:"+id+"\\s+(H264|H265|HEVC)/90000\\s*$").matcher(block);
                    if(!m.find())continue;
                    Track t=new Track();t.payload=Integer.parseInt(id);t.hevc=!m.group(1).equalsIgnoreCase("H264");
                    t.path=attribute(block,"control");t.aggregate=agg;
                    Matcher fmt=Pattern.compile("(?im)^a=fmtp:"+id+"[ \\t]+(.+)$").matcher(block);
                    if(fmt.find()){
                        for(String pair:fmt.group(1).split(";")){
                            String[] kv=pair.trim().split("=",2);
                            if(kv.length!=2 || !Arrays.asList("sprop-parameter-sets","sprop-sps","sprop-pps","sprop-vps").contains(kv[0]))continue;
                            for(String v:kv[1].split(","))try{t.parameters.add(Base64.getDecoder().decode(v.trim()));}catch(IllegalArgumentException ignored){}
                        }
                    }
                    return t;
                }
            }
            throw new IOException("A câmera não anunciou vídeo H.264 ou H.265.");
        }
        int sampleRate;
        static Track audio(String sdp)throws IOException{
            String[] sections=sdp.replace("\r","").split("(?m)^m=");
            for(int i=1;i<sections.length;i++){
                String block=sections[i];
                String[] fields=block.split("\n",2)[0].trim().split("\\s+");
                if(fields.length<4 || !fields[0].equals("audio"))continue;
                for(int j=3;j<fields.length;j++){
                    if(!fields[j].matches("[0-9]{1,3}"))continue;
                    int id=Integer.parseInt(fields[j]);
                    if(id>127)continue;
                    Matcher map=Pattern.compile("(?im)^a=rtpmap:"+id+"[ \\t]+([^\\s]+)").matcher(block);
                    int rate=8000;
                    if(map.find()){
                        Matcher format=Pattern.compile("(?i)PCMA/([0-9]{4,5})(?:/1)?").matcher(map.group(1));
                        if(!format.matches())continue;
                        rate=Integer.parseInt(format.group(1));
                        if(rate<8000 || rate>48000)continue;
                    }else if(id!=8)continue;
                    Track track=new Track();
                    track.payload=id;track.sampleRate=rate;track.path=attribute(block,"control");
                    track.aggregate=attribute(sections[0],"control");
                    return track;
                }
            }
            throw new IOException("A câmera não anunciou áudio mono G.711 A-law.");
        }
        static String attribute(String section,String key){
            Matcher m=Pattern.compile("(?m)^a="+key+":(.+)$").matcher(section);
            return m.find()?m.group(1).trim():"";
        }
    }
    private URI local(URI base,String value)throws IOException{
        if(value.isEmpty() || value.equals("*"))return base;
        URI ref=URI.create(value);
        URI resolved=base.resolve(ref);
        if(!"rtsp".equalsIgnoreCase(resolved.getScheme()) || resolved.getFragment()!=null)
            throw new IOException("Endereço de controle RTSP inválido.");
        // The socket and credentials belong exclusively to the camera the user entered.
        return URI.create("rtsp://"+url.getRawAuthority()+resolved.getRawPath()+
            (resolved.getRawQuery()==null?"":"?"+resolved.getRawQuery()));
    }
    void play(Listener listener)throws Exception{
        run(new Receiver(){
            private RtpVideo parser;
            public boolean active(){return listener.active();}
            public Track select(String sdp)throws Exception{
                Track track=Track.parse(sdp);
                listener.format(track.hevc,track.parameters);
                parser=new RtpVideo(track.hevc,track.payload,listener::frame);
                return track;
            }
            public void packet(byte[] data,int length)throws Exception{parser.packet(data,length);}
        });
    }
    void listen(AudioListener listener)throws Exception{
        run(new Receiver(){
            private final PcmaRtp decoder=new PcmaRtp();
            public boolean active(){return listener.active();}
            public Track select(String sdp)throws Exception{
                Track track=Track.audio(sdp);
                listener.format(track.sampleRate);
                return track;
            }
            public void packet(byte[] data,int length)throws Exception{
                int count=decoder.decode(data,length);
                if(count>0)listener.packetSamples(decoder.pcm,count,((long)RtpVideo.u16(data,4)<<16)|RtpVideo.u16(data,6));
            }
        });
    }
    private void run(Receiver listener)throws Exception{
        if(!listener.active())return;
        try{
            connect();
            request("OPTIONS",url,"");
            DiagnosticoRtsp.Reply desc=request("DESCRIBE",url,"Accept: application/sdp\r\n");
            Track media=listener.select(desc.body);
            URI base=desc.base.isEmpty()?url:local(url,desc.base);
            URI trackBase=base;
            if(!base.getPath().endsWith("/"))trackBase=URI.create("rtsp://"+url.getRawAuthority()+base.getRawPath()+"/");
            URI track=media.path.isEmpty() || media.path.equals("*")?base:local(trackBase,media.path);
            URI aggregate=local(base,media.aggregate);

            for(int attempt=0;attempt<32;attempt++){
                if(!listener.active())return;
                try(DatagramSocket rtp=new DatagramSocket(0,control.getLocalAddress())){
                    int port=rtp.getLocalPort();
                    if((port&1)!=0 || port>=65535)continue;
                    DatagramSocket second;
                    try{second=new DatagramSocket(port+1,control.getLocalAddress());}catch(BindException e){continue;}
                    try(DatagramSocket rtcp=second){
                        receive(listener,media,track,aggregate,rtp);
                    }
                    return;
                }
            }
            throw new IOException("Sem par de portas UDP disponível.");
        }finally{
            if(control!=null){
                try{if(!session.isEmpty()){
                    control.setSoTimeout(400);
                    request("TEARDOWN",url,"");
                }}catch(Exception ignored){}finally{control.close();}
            }
        }
    }
    private void receive(Receiver listener,Track track,URI path,URI aggregate,DatagramSocket rtp)throws Exception{
        rtp.setReceiveBufferSize(2*1024*1024);rtp.setSoTimeout(300);
        int port=rtp.getLocalPort();
        DiagnosticoRtsp.Reply setup=request("SETUP",path,"Transport: RTP/AVP/UDP;unicast;client_port="+port+"-"+(port+1)+"\r\n");
        String[] fields=setup.session.split(";");
        session=fields[0].trim();
        if(session.isEmpty() || !session.matches("[!-~]{1,256}"))throw new IOException("SETUP sem sessão válida.");
        if(setup.transport.toUpperCase(Locale.ROOT).contains("TCP"))throw new IOException("A câmera recusou RTP por UDP.");
        for(String f:fields)if(f.trim().matches("timeout=[0-9]{1,6}"))keepAliveSeconds=Math.max(1,Math.min(20,Integer.parseInt(f.trim().substring(8))/2));
        request("PLAY",aggregate,"Range: npt=0.000-\r\n");

        try(RtpInbox inbox=new RtpInbox(rtp,control.getInetAddress(),track.payload)){
            long last=System.nanoTime(),alive=last;
            while(listener.active()){
                byte[] packet=inbox.poll();
                if(packet!=null){last=System.nanoTime();listener.packet(packet,packet.length);}
                long now=System.nanoTime();
                if(now-last>8_000_000_000L)throw new IOException("PLAY aceito. Nenhum pacote de mídia UDP recebido nos últimos 8 s.");
                if(now-alive>keepAliveSeconds*1_000_000_000L){request("OPTIONS",aggregate,"");alive=System.nanoTime();}
            }
        }
    }
}
