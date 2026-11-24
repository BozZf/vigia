package br.vigia.mobile;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.regex.*;

/** Read the selected stream's SDP after a player error. Never persist or display a stream URI. */
final class DiagnosticoRtsp {
    static URI enderecoSemUsuario(URI uri) {
        String path=uri.getRawPath();
        return URI.create("rtsp://"+uri.getHost()+(uri.getPort()<0?"":":"+uri.getPort())+
            (path.isEmpty()?"/":path)+(uri.getRawQuery()==null?"":"?"+uri.getRawQuery()));
    }

    static final class Reply {
        int status, length;
        boolean close;
        String challenge="";
        String body="";
    }
    private static String line(InputStream in,int[] remaining) throws IOException {
        ByteArrayOutputStream buffer=new ByteArrayOutputStream();
        while(remaining[0]-- > 0){
            int b=in.read();
            if(b<0)throw new EOFException();
            if(b=='\n')return buffer.toString("ISO-8859-1");
            if(b!='\r')buffer.write(b);
        }
        throw new IOException();
    }
    static Reply read(InputStream raw) throws IOException {
        DataInputStream in=new DataInputStream(new BufferedInputStream(raw));
        int[] budget={16384};
        String[] first=line(in,budget).split(" ",3);
        if(first.length<2 || !first[0].startsWith("RTSP/"))throw new IOException();
        Reply r=new Reply();r.status=Integer.parseInt(first[1]);
        String header;
        while(!(header=line(in,budget)).isEmpty()){
            int sep=header.indexOf(':');if(sep<=0)continue;
            String key=header.substring(0,sep).trim(), val=header.substring(sep+1).trim();
            if(key.equalsIgnoreCase("Connection") && "close".equalsIgnoreCase(val))r.close=true;
            if(key.equalsIgnoreCase("Content-Length"))r.length=Integer.parseInt(val);
            if(key.equalsIgnoreCase("WWW-Authenticate") && (r.challenge.isEmpty() || val.regionMatches(true,0,"Digest ",0,7)))r.challenge=val;
        }
        if(r.length<0 || r.length>65536)throw new IOException();
        if(r.length>0){
            byte[] data=new byte[r.length];in.readFully(data);r.body=new String(data,StandardCharsets.UTF_8);
        }
        return r;
    }
    static String video(String sdp){
        boolean video=false;
        Set<String> payloads=new HashSet<>();
        Set<String> codecs=new LinkedHashSet<>();
        Pattern mapping=Pattern.compile("a=rtpmap:(\\d+)\\s+([A-Za-z0-9._-]{1,24})/",Pattern.CASE_INSENSITIVE);
        for(String row:sdp.split("\r?\n")){
            String s=row.trim();
            if(s.startsWith("m=")){
                String[] fields=s.split("\\s+");
                video=s.startsWith("m=video ") && fields.length>=4;
                payloads.clear();
                if(video)payloads.addAll(Arrays.asList(fields).subList(3,fields.length));
            }else if(video){
                Matcher m=mapping.matcher(s);
                if(m.lookingAt() && payloads.contains(m.group(1)))codecs.add(m.group(2).toUpperCase(Locale.ROOT));
            }
        }
        return String.join(", ",codecs);
    }
    interface Exchange { Reply describe(URI target, int seq, String auth) throws IOException; }
    static String inspect(URI uri, Exchange transport) throws Exception {
        URI clean=enderecoSemUsuario(uri);
        String[] login=uri.getRawUserInfo()==null?new String[0]:uri.getRawUserInfo().split(":",2);
        String auth=null;
        for(int seq=1;seq<=2;seq++){
            Reply reply=transport.describe(clean,seq,auth);
            if(reply.status==401 && seq==1 && login.length==2){
                String u=URLDecoder.decode(login[0],"UTF-8"),p=URLDecoder.decode(login[1],"UTF-8");
                auth=CameraOnvif.digestHeader(reply.challenge,"DESCRIBE",clean.toASCIIString(),u,p);
                if(auth==null && reply.challenge.regionMatches(true,0,"Basic ",0,6))
                    auth="Basic "+Base64.getEncoder().encodeToString((u+":"+p).getBytes(StandardCharsets.UTF_8));
                if(auth!=null)continue;
            }
            if(reply.status==200){
                String codec=video(reply.body);
                return "RTSP respondeu 200"+(codec.isEmpty()?"":" · vídeo "+codec)+".";
            }
            if(reply.status==401 || reply.status==403)return "RTSP recusou o acesso ("+reply.status+").";
            if(reply.status==404)return "RTSP não encontrou o fluxo (404).";
            return "A câmera respondeu RTSP "+reply.status+".";
        }
        throw new IOException();
    }
    private static final class Session implements Exchange, Closeable {
        Socket socket;
        public void close() throws IOException {
            if(socket!=null){socket.close();socket=null;}
        }
        public Reply describe(URI target,int seq,String auth) throws IOException {
            if(socket==null){
                socket=new Socket(Proxy.NO_PROXY);
                socket.connect(new InetSocketAddress(target.getHost(),target.getPort()<0?554:target.getPort()),2500);
                socket.setSoTimeout(3000);
            }
            String req="DESCRIBE "+target.toASCIIString()+" RTSP/1.0\r\nCSeq: "+seq+"\r\nAccept: application/sdp\r\n"+
                (auth==null?"":"Authorization: "+auth+"\r\n")+"\r\n";
            socket.getOutputStream().write(req.getBytes(StandardCharsets.UTF_8));
            Reply r=read(socket.getInputStream());
            if(r.close)close();
            return r;
        }
    }
    static String inspect(URI uri){
        try(Session session=new Session()){
            return inspect(uri,session);
        }catch(SocketTimeoutException ex){return "RTSP não respondeu no prazo.";}
        catch(ConnectException | NoRouteToHostException ex){return "Sem conexão com a porta RTSP anunciada.";}
        catch(Exception ex){return "Não foi possível confirmar a descrição RTSP do fluxo.";}
    }
}
