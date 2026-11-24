package br.vigia.mobile;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.*;
import java.util.*;
import java.util.regex.*;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.*;
import org.xml.sax.InputSource;

/** ONVIF Media1, restricted to the single camera entered by the owner. */
final class CameraOnvif {
    static final String DEVICE = "http://www.onvif.org/ver10/device/wsdl";
    static final String MEDIA = "http://www.onvif.org/ver10/media/wsdl";
    private static final String SCHEMA = "http://www.onvif.org/ver10/schema";
    private static final String WS = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-";
    private static final SecureRandom RANDOM = new SecureRandom();
    private final URI device;
    private final String user, pass;
    private URI media;
    private long offsetSeconds;
    private volatile boolean cancelled;
    private volatile HttpURLConnection current;

    CameraOnvif(String address, String user, String pass) throws IOException {
        device = address(address);
        this.user = user.trim(); this.pass = pass;
    }
    static URI address(String text) throws IOException {
        try {
            String value = text.trim();
            URI u = URI.create(value.contains("://") ? value : "http://" + value);
            String host = u.getHost();
            if (host == null || !host.matches("(?:[0-9]{1,3}\\.){3}[0-9]{1,3}")) throw new IllegalArgumentException();
            String[] parts = host.split("\\.");
            for (String part : parts) if (Integer.parseInt(part)>255 || (part.length()>1 && part.startsWith("0"))) throw new IllegalArgumentException();
            int first=Integer.parseInt(parts[0]), second=Integer.parseInt(parts[1]);
            if (!(first==10 || first==192 && second==168 || first==172 && second>=16 && second<=31 || first==169 && second==254)) throw new IllegalArgumentException();
            if (!Arrays.asList("http","https").contains(u.getScheme()) || u.getUserInfo()!=null ||
                u.getQuery()!=null || u.getFragment()!=null || u.getPort()==0 || u.getPort()>65535) throw new IllegalArgumentException();
            int port = u.getPort();
            if (port<0 && !value.contains("://")) port=5000;
            String path=u.getPath();
            return new URI(u.getScheme(),null,host,port,path.isEmpty() || path.equals("/")?"/onvif/device_service":path,null,null);
        } catch(Exception e) { throw new IOException("Informe o IPv4 local da câmera. Você pode incluir a porta ONVIF."); }
    }
    void cancel() {
        cancelled=true;
        HttpURLConnection c=current;
        if(c!=null)c.disconnect();
    }
    static final class Profile {
        final String token, source, label;
        Profile(String token,String source,String label){this.token=token;this.source=source;this.label=label;}
    }
    List<Profile> profiles() throws Exception {
        try {
            Element clock = request(device,DEVICE,"GetSystemDateAndTime","",false);
            Element utc=first(clock,"UTCDateTime");
            if(utc!=null) {
                LocalDateTime dt=LocalDateTime.of(number(utc,"Year"),number(utc,"Month"),number(utc,"Day"),
                    number(utc,"Hour"),number(utc,"Minute"),number(utc,"Second"));
                offsetSeconds=dt.toEpochSecond(ZoneOffset.UTC)-Instant.now().getEpochSecond();
            }
        } catch(IOException | RuntimeException ignored) { /* Optional camera clock. */ }
        Element caps=request(device,DEVICE,"GetCapabilities","<m:Category>Media</m:Category>",true);
        String location=text(first(caps,"Media"),"XAddr");
        if(location.isEmpty()) throw new IOException("A câmera respondeu, mas não anunciou o serviço de vídeo ONVIF Media1.");
        media=sameCamera(location,false);
        return parseProfiles(request(media,MEDIA,"GetProfiles","",true));
    }
    static List<Profile> parseProfiles(Element reply) throws IOException {
        List<Profile> found=new ArrayList<>();
        NodeList nodes=reply.getElementsByTagNameNS("*","Profiles");
        for(int i=0;i<nodes.getLength() && found.size()<32;i++){
            Element p=(Element)nodes.item(i);
            String token=p.getAttribute("token"); if(token.isEmpty())continue;
            String name=text(p,"Name");
            Element enc=first(p,"VideoEncoderConfiguration");
            String size=text(enc,"Width"), height=text(enc,"Height");
            String label=(name.isEmpty()?"Perfil "+(i+1):name)+(size.isEmpty()?"":" · "+size+"×"+height);
            found.add(new Profile(token,text(first(p,"VideoSourceConfiguration"),"SourceToken"),label));
        }
        if(found.isEmpty())throw new IOException("O serviço de vídeo não retornou perfis.");
        return found;
    }
    URI stream(Profile p) throws Exception {
        String body="<m:StreamSetup><t:Stream>RTP-Unicast</t:Stream><t:Transport><t:Protocol>RTSP</t:Protocol></t:Transport></m:StreamSetup><m:ProfileToken>"+escape(p.token)+"</m:ProfileToken>";
        Element reply=request(media,MEDIA,"GetStreamUri",body,true);
        return sameCamera(text(reply,"Uri"),true);
    }
    URI sameCamera(String address, boolean rtsp) throws IOException {
        try {
            URI u=device.resolve(address.trim());
            if(address.trim().isEmpty() || u.getHost()==null ||
                u.getFragment()!=null || u.getPort()==0 || u.getPort()>65535 ||
                !(rtsp?"rtsp".equalsIgnoreCase(u.getScheme()):Arrays.asList("http","https").contains(u.getScheme())) ||
                (!rtsp && device.getScheme().equals("https") && !u.getScheme().equals("https"))) throw new IllegalArgumentException();
            // Preserve the camera's encoded path/query, use only the entered host and credentials.
            String auth=rtsp && !user.isEmpty()?pct(user)+":"+pct(pass)+"@":"";
            return URI.create(u.getScheme()+"://"+auth+device.getHost()+(u.getPort()<0?"":":"+u.getPort())+
                u.getRawPath()+(u.getRawQuery()==null?"":"?"+u.getRawQuery()));
        } catch(Exception e){throw new IOException("O endereço anunciado pela câmera é incompatível com esta conexão.");}
    }
    private static String pct(String value) throws UnsupportedEncodingException {
        return URLEncoder.encode(value,"UTF-8").replace("+","%20");
    }
    private static int number(Element e,String key){return Integer.parseInt(text(e,key));}
    private static Element first(Element p,String key){
        return p==null?null:(Element)p.getElementsByTagNameNS("*",key).item(0);
    }
    private static String text(Element e,String key){Element item=first(e,key);return item==null?"":item.getTextContent().trim();}
    private static String escape(String s){return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;");}
    static Element xml(String raw) throws IOException {
        if(raw.contains("<!DOCTYPE") || raw.contains("<!ENTITY"))throw new IOException("Resposta XML inválida.");
        try {
            DocumentBuilderFactory factory=DocumentBuilderFactory.newInstance();
            factory.setNamespaceAware(true);
            return factory.newDocumentBuilder().parse(new InputSource(new StringReader(raw))).getDocumentElement();
        }catch(Exception e){throw new IOException("Resposta ONVIF inválida.");}
    }
    private String security() throws Exception {
        byte[] nonce=new byte[20];RANDOM.nextBytes(nonce);
        String date=Instant.ofEpochSecond(Instant.now().getEpochSecond()+offsetSeconds).toString();
        MessageDigest hash=MessageDigest.getInstance("SHA-1");
        hash.update(nonce);hash.update(date.getBytes(StandardCharsets.UTF_8));
        String digest=Base64.getEncoder().encodeToString(hash.digest(pass.getBytes(StandardCharsets.UTF_8)));
        return "<s:Header><w:Security xmlns:w='"+WS+"wssecurity-secext-1.0.xsd' xmlns:u='"+WS+"wssecurity-utility-1.0.xsd'><w:UsernameToken><w:Username>"+
          escape(user)+"</w:Username><w:Password Type='"+WS+"username-token-profile-1.0#PasswordDigest'>"+digest+
          "</w:Password><w:Nonce EncodingType='"+WS+"soap-message-security-1.0#Base64Binary'>"+Base64.getEncoder().encodeToString(nonce)+
          "</w:Nonce><u:Created>"+date+"</u:Created></w:UsernameToken></w:Security></s:Header>";
    }
    private Element request(URI uri,String namespace,String method,String body,boolean auth) throws Exception {
        String msg="<s:Envelope xmlns:s='http://www.w3.org/2003/05/soap-envelope' xmlns:m='"+namespace+"' xmlns:t='"+SCHEMA+"'>"+
            (auth && !user.isEmpty()?security():"")+"<s:Body><m:"+method+">"+body+"</m:"+method+"></s:Body></s:Envelope>";
        String authorization=null;
        for(int attempt=0;attempt<2;attempt++){
            if(cancelled)throw new IOException("Teste encerrado.");
            HttpURLConnection c=(HttpURLConnection)uri.toURL().openConnection(Proxy.NO_PROXY);
            current=c;
            try {
                if(cancelled)throw new IOException("Teste encerrado.");
                c.setInstanceFollowRedirects(false);c.setConnectTimeout(3500);c.setReadTimeout(4500);
                c.setRequestMethod("POST");c.setDoOutput(true);
                c.setRequestProperty("Content-Type","application/soap+xml; charset=utf-8; action=\""+namespace+"/"+method+"\"");
                if(authorization!=null)c.setRequestProperty("Authorization",authorization);
                try(OutputStream out=c.getOutputStream()){out.write(msg.getBytes(StandardCharsets.UTF_8));}
                int code=c.getResponseCode();
                if(code==401 && attempt==0 && auth && !user.isEmpty()){
                    authorization=digestHeader(c.getHeaderField("WWW-Authenticate"),uri,user,pass);
                    if(authorization!=null)continue;
                }
                if(code==401 || code==403)throw new IOException(method+": acesso recusado. Confira o usuário e a senha NVR/RTSP.");
                if(code>=300 && code<400)throw new IOException(method+": endereço ONVIF redirecionado.");
                InputStream input=code>=400?c.getErrorStream():c.getInputStream();
                if(input==null)throw new IOException(method+": HTTP "+code+".");
                ByteArrayOutputStream data=new ByteArrayOutputStream();
                try(InputStream in=input){
                    byte[] buf=new byte[4096];int n;
                    while((n=in.read(buf))!=-1){
                        if(data.size()+n>1024*1024)throw new IOException("Resposta ONVIF grande demais.");
                        data.write(buf,0,n);
                    }
                }
                Element reply=xml(data.toString("UTF-8"));
                Element fault=first(reply,"Fault");
                if(fault!=null || code>=400){
                    String reason=fault==null?"":fault.getTextContent().toLowerCase(Locale.ROOT);
                    throw new IOException(method+(reason.contains("authoriz") || reason.contains("authentic")?": autenticação recusada. Confira a senha NVR/RTSP.":": a câmera recusou a operação (HTTP "+code+")."));
                }
                if(first(reply,method+"Response")==null)throw new IOException(method+": resposta ONVIF inesperada.");
                return reply;
            } catch(SocketTimeoutException e){throw new IOException(method+": tempo esgotado. Confira IP, porta e Wi-Fi.");}
              catch(ConnectException | NoRouteToHostException e){throw new IOException(method+": sem conexão. Confira IP, porta e Wi-Fi.");}
            finally{current=null;c.disconnect();}
        }
        throw new IOException(method+": autenticação recusada.");
    }
    private static String hash(String algorithm,String text) throws Exception {
        byte[] raw=MessageDigest.getInstance(algorithm).digest(text.getBytes(StandardCharsets.UTF_8));
        StringBuilder str=new StringBuilder();for(byte b:raw)str.append(String.format(Locale.ROOT,"%02x",b&255));return str.toString();
    }
    private static String quote(String s){return "\""+s.replace("\\","\\\\").replace("\"","\\\"")+"\"";}
    static String digestHeader(String challenge,URI uri,String user,String pass) throws Exception {
        if(challenge==null || !challenge.regionMatches(true,0,"Digest ",0,7))return null;
        Map<String,String> m=new HashMap<>();
        Matcher it=Pattern.compile("(\\w+)\\s*=\\s*(?:\"([^\"]*)\"|([^,\\s]+))").matcher(challenge.substring(7));
        while(it.find())m.put(it.group(1).toLowerCase(Locale.ROOT),it.group(2)!=null?it.group(2):it.group(3));
        String realm=m.get("realm"),nonce=m.get("nonce"),algorithm=m.getOrDefault("algorithm","MD5");
        if(realm==null || nonce==null || !(algorithm.equalsIgnoreCase("MD5") || algorithm.equalsIgnoreCase("SHA-256")))return null;
        if(user.contains("\r")||user.contains("\n"))throw new IOException("Usuário inválido.");
        String target=uri.getRawPath()+(uri.getRawQuery()==null?"":"?"+uri.getRawQuery());
        String a1=hash(algorithm,user+":"+realm+":"+pass), a2=hash(algorithm,"POST:"+target);
        String mid="",extra="";
        if(m.containsKey("qop")){
            if(!Arrays.asList(m.get("qop").toLowerCase(Locale.ROOT).split("\\s*,\\s*")).contains("auth"))return null;
            String cn=UUID.randomUUID().toString();
            mid="00000001:"+cn+":auth:";
            extra=", qop=auth, nc=00000001, cnonce="+quote(cn);
        }
        return "Digest username="+quote(user)+", realm="+quote(realm)+", nonce="+quote(nonce)+", uri="+quote(target)+
            ", response="+quote(hash(algorithm,a1+":"+nonce+":"+mid+a2))+", algorithm="+algorithm+extra+
            (m.containsKey("opaque")?", opaque="+quote(m.get("opaque")):"");
    }
}
