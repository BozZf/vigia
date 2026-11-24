package br.vigia.mobile;
import java.io.*;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.security.MessageDigest;

public final class DiagnosticoRtspTest {
    static void check(boolean ok){if(!ok)throw new AssertionError();}
    static DiagnosticoRtsp.Reply reply(int status,String headers,String body)throws IOException{
        String response="RTSP/1.0 "+status+" Test\r\n"+headers+"Content-Length: "+body.length()+"\r\n\r\n"+body;
        return DiagnosticoRtsp.read(new ByteArrayInputStream(response.getBytes(StandardCharsets.US_ASCII)));
    }
    static String md5(String value)throws Exception{
        StringBuilder s=new StringBuilder();
        for(byte b:MessageDigest.getInstance("MD5").digest(value.getBytes(StandardCharsets.UTF_8)))s.append(String.format("%02x",b&255));
        return s.toString();
    }
    static String profile(String name,String source,int w,int h){
        return "<Profiles token='"+name+"'><Name>"+name+"</Name><VideoSourceConfiguration><SourceToken>"+source+
            "</SourceToken></VideoSourceConfiguration><VideoEncoderConfiguration><Resolution><Width>"+w+"</Width><Height>"+h+
            "</Height></Resolution></VideoEncoderConfiguration></Profiles>";
    }
    public static void main(String[] args)throws Exception {
        String xml="<reply>"+profile("main","one",1920,2160)+profile("sub","one",640,720)+profile("two","two",320,240)+"</reply>";
        List<CameraOnvif.Profile> p=CameraOnvif.parseProfiles(CameraOnvif.xml(xml));
        check(CameraOnvif.lightest(p,"one")==p.get(1));check(CameraOnvif.lightest(p,"two")==p.get(2));
        URI rtsp=URI.create("rtsp://test:a%3Ab@192.168.1.5:554/c%2F1?profile=sub");
        String target="rtsp://192.168.1.5:554/c%2F1?profile=sub";
        String response=md5(md5("test:cam:a:b")+":abc:"+md5("DESCRIBE:"+target));
        String codec="m=video 0 RTP/AVP 96\r\na=rtpmap:96 H265/90000\r\na=rtpmap:99 other/90000\r\nm=audio 0 RTP/AVP 97\r\na=rtpmap:97 OPUS/48000\r\n";
        int[] calls={0};
        String result=DiagnosticoRtsp.inspect(rtsp,(u,seq,auth)->{
            check(u.toASCIIString().equals(target));calls[0]++;
            if(seq==1){check(auth==null);return reply(401,"WWW-Authenticate: Digest realm=\"cam\", nonce=\"abc\"\r\n","");}
            check(auth.contains(response) && !auth.contains("a:b"));return reply(200,"",codec);
        });
        check(calls[0]==2 && result.equals("RTSP respondeu 200 · vídeo H265."));
        check(DiagnosticoRtsp.inspect(rtsp,(u,seq,auth)->reply(404,"","")).contains("404"));
        check(DiagnosticoRtsp.inspect(rtsp,(u,seq,auth)->reply(403,"","")).contains("403"));
        check(DiagnosticoRtsp.enderecoSemUsuario(rtsp).toString().equals(target));
        System.out.println("OK: perfil menor por fonte, DESCRIBE autenticado, SDP de vídeo, 403 e 404.");
    }
}
