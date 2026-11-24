package br.vigia.mobile;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class CameraOnvifTest {
    private static final String IP="192.168.0.8";
    private static final List<String> calls=new ArrayList<>();
    private static boolean deny,badPhoto;
    private static void check(boolean ok){if(!ok)throw new AssertionError();}
    private static final class Camera extends HttpURLConnection {
        final ByteArrayOutputStream out=new ByteArrayOutputStream();
        Camera(URL u){super(u);check(IP.equals(u.getHost()));}
        public void connect(){} public void disconnect(){} public boolean usingProxy(){return false;}
        public OutputStream getOutputStream(){return out;}
        String action(){if("GET".equals(getRequestMethod()))return "photo";String s=getRequestProperty("Content-Type");return s.substring(s.lastIndexOf('/')+1,s.length()-1);}
        public int getResponseCode(){
            calls.add(action());
            if(action().equals("photo")){
                if(getInstanceFollowRedirects() || getUseCaches())throw new AssertionError();
                return getRequestProperty("Authorization")==null?401:200;
            }
            return action().equals("GetProfiles") && (deny || getRequestProperty("Authorization")==null)?401:200;
        }
        public String getHeaderField(String n){return "Digest realm=\"camera\", nonce=\"abc\", qop=\"auth\", algorithm=MD5";}
        public InputStream getInputStream(){
            String a=action(), fields="";
            switch(a){
            case "photo":
                check(url.getPath().equals("/snapshot") && getRequestProperty("Authorization").contains("uri=\"/snapshot?view=2\""));
                return new ByteArrayInputStream(badPhoto?new byte[]{1,2,3}:new byte[]{-1,-40,-1,1});
            case "GetSnapshotUri":
                check(out.toString().contains("lower"));
                fields="<Uri>http://wrong.invalid:5070/snapshot?view=2</Uri>";break;
            case "GetSystemDateAndTime": fields="<UTCDateTime><Year>2026</Year><Month>11</Month><Day>23</Day><Hour>12</Hour><Minute>30</Minute><Second>15</Second></UTCDateTime>";break;
            case "GetCapabilities":fields="<Media><XAddr>http://wrong.invalid:5000/media</XAddr></Media>";break;
            case "GetProfiles":
                check(getRequestProperty("Authorization").startsWith("Digest "));
                fields=profile("hd","upper")+profile("sd","upper")+profile("lower","lower");break;
            case "GetStreamUri":
                check(out.toString().contains("lower") && !out.toString().contains("s&amp;cret"));
                fields="<Uri>rtsp://wrong.invalid:554/path%2Fone?q=a%20b</Uri>";break;
            default:throw new AssertionError();
            }
            if(!a.equals("GetSystemDateAndTime"))check(out.toString().contains("PasswordDigest"));
            String xml="<s:Envelope xmlns:s='http://www.w3.org/2003/05/soap-envelope'><s:Body><"+a+"Response>"+fields+"</"+a+"Response></s:Body></s:Envelope>";
            return new ByteArrayInputStream(xml.getBytes(StandardCharsets.UTF_8));
        }
        String profile(String token,String source){return "<Profiles token='"+token+"'><Name>"+token+"</Name><VideoSourceConfiguration><SourceToken>"+source+"</SourceToken></VideoSourceConfiguration></Profiles>";}
    }
    public static void main(String[] args)throws Exception {
        URL.setURLStreamHandlerFactory(protocol->protocol.equals("http")?new URLStreamHandler(){
            protected URLConnection openConnection(URL u){return new Camera(u);}
            protected URLConnection openConnection(URL u,Proxy proxy){return new Camera(u);}
        }:null);
        for(String bad:Arrays.asList("example.com","8.8.8.8","10.2.3.256","http://me:pw@192.168.1.3","127.0.0.1")){
            try{CameraOnvif.address(bad);throw new AssertionError();}catch(IOException expected){}
        }
        CameraOnvif client=new CameraOnvif(IP,"local","s&cret");
        check(CameraOnvif.address(IP).getPort()==5000);
        List<CameraOnvif.Profile> p=client.profiles();
        check(p.size()==3 && p.get(0).source.equals(p.get(1).source) && !p.get(0).source.equals(p.get(2).source));
        URI stream=client.stream(p.get(2));check(stream.getHost().equals(IP) && stream.getRawPath().equals("/path%2Fone") && stream.getRawQuery().equals("q=a%20b") && stream.getUserInfo().equals("local:s&cret"));
        check(calls.equals(Arrays.asList("GetSystemDateAndTime","GetCapabilities","GetProfiles","GetProfiles","GetStreamUri")));
        check(client.snapshot(p.get(2))[0]==-1);
        badPhoto=true;
        try{client.snapshot(p.get(2));throw new AssertionError();}catch(IOException expected){check(expected.getMessage().contains("JPEG"));}
        CameraOnvif.Profile sub=new CameraOnvif.Profile("s","","SubStream","sub",100);
        URI direct=client.directStream(sub,stream);
        check(direct.getHost().equals(IP) && direct.getPort()==554 && direct.getPath().equals("/onvif2") && direct.getUserInfo().equals("local:s&cret"));
        check(client.directStream(sub,direct)==null && client.directStream(p.get(0),stream)==null);
        check(client.directStream(new CameraOnvif.Profile("m","","MainStream","main",200),null).getPath().equals("/onvif1"));
        deny=true;
        try{client.profiles();throw new AssertionError();}catch(IOException expected){check(expected.getMessage().contains("acesso recusado"));}
        client.cancel();try{client.profiles();throw new AssertionError();}catch(IOException expected){check(expected.getMessage().contains("encerrado"));}
        try{CameraOnvif.xml("<!DOCTYPE a><a/>");throw new AssertionError();}catch(IOException expected){}
        System.out.println("OK: perfis, fontes, relógio, autenticação, endereço retornado, rejeição e cancelamento.");
    }
}
