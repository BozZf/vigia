package br.vigia.mobile;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.net.Uri;
import android.view.View;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.media.MediaPlayer;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.ViewGroup;
import android.widget.*;
import java.io.IOException;
import java.net.URI;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class CameraLocal extends Activity {
    private static final int INK=0xffeff5f3, SUB=0xffbac9c5, BG=0xff171b23;
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private final Handler main=new Handler();
    private final ExecutorService diagnostics=Executors.newFixedThreadPool(2);
    private CameraOnvif camera;
    private EditText address, user, password;
    private TextView status;
    private LinearLayout root, options;
    private Button connect;
    private final Pane[] panes=new Pane[2];
    private int session;

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        ScrollView scroll=new ScrollView(this);
        root=new LinearLayout(this);root.setOrientation(1);root.setBackgroundColor(BG);
        int pad=dp(15);root.setPadding(pad,pad,pad,pad);scroll.addView(root);setContentView(scroll);
        label(root,"Câmera no Wi-Fi",24);
        label(root,"Use o mesmo Wi-Fi da câmera. Informe o endereço local e a senha de conexão NVR/RTSP.",15);
        address=field("IP ou endereço ONVIF","Ex.: 192.168.1.50:5000",17);
        user=field("Usuário local","Usuário da câmera",1);user.setText("administrator");
        password=field("Senha NVR/RTSP","Senha local da câmera",129);
        connect=button(root,"Conectar à câmera");connect.setOnClickListener(v->{if(camera==null)begin();else stopSession();});
        status=label(root,"Aguardando conexão.",15);
        for(int i=0;i<2;i++)panes[i]=new Pane(i+1);
        options=new LinearLayout(this);options.setOrientation(1);root.addView(options);
    }
    private int dp(int x){return Math.round(x*getResources().getDisplayMetrics().density);}
    private TextView label(LinearLayout parent,String title,int size){
        TextView v=new TextView(this);v.setText(title);v.setTextColor(size>17?INK:SUB);v.setTextSize(size);
        v.setPadding(0,dp(5),0,dp(3));parent.addView(v);return v;
    }
    private EditText field(String title,String hint,int type){
        label(root,title,14); EditText v=new EditText(this);v.setSingleLine(true);v.setInputType(type);
        v.setHint(hint);v.setHintTextColor(SUB);v.setTextColor(INK);root.addView(v);return v;
    }
    private Button button(LinearLayout parent,String title){
        Button b=new Button(this);b.setText(title);b.setAllCaps(false);parent.addView(b);return b;
    }
    private void setInputs(boolean enabled){
        address.setEnabled(enabled);user.setEnabled(enabled);password.setEnabled(enabled);
        connect.setText(enabled?"Conectar à câmera":"Desconectar");
    }
    private void begin(){
        try{camera=new CameraOnvif(address.getText().toString(),user.getText().toString(),password.getText().toString());}
        catch(IOException e){status.setText(e.getMessage());return;}
        int id=++session;CameraOnvif client=camera;
        setInputs(false);status.setText("Consultando os perfis ONVIF…");
        worker.execute(()->{
            try{
                List<CameraOnvif.Profile> list=client.profiles();
                runOnUiThread(()->{if(id==session)showProfiles(list);});
            }catch(Exception ex){runOnUiThread(()->{if(id==session){stopSession();status.setText(message(ex));}});}
        });
    }
    private static String message(Exception ex){
        // Only errors created by the ONVIF client are suitable for the status panel.
        if(ex.getClass()==IOException.class && ex.getMessage()!=null)return ex.getMessage();
        return "Falha de comunicação com o serviço de vídeo local.";
    }
    private void showProfiles(List<CameraOnvif.Profile> list){
        CameraOnvif.Profile first=CameraOnvif.lightest(list,list.get(0).source), second=null;
        for(CameraOnvif.Profile p:list){
            if(!first.source.isEmpty() && !p.source.isEmpty() && !p.source.equals(first.source)){
                second=CameraOnvif.lightest(list,p.source);break;
            }
        }
        status.setText(list.size()+" perfil(is) recebido(s). Abrindo "+first.label+". "+
            (second!=null?"Duas fontes distintas anunciadas.":
            "Os perfis podem ser qualidades da mesma imagem. Confira se o visor mostra as duas cenas."));
        label(options,"Perfis da câmera",19);
        for(CameraOnvif.Profile p:list){
            label(options,p.label,15);
            LinearLayout row=new LinearLayout(this);options.addView(row);
            for(int i=0;i<2;i++){final int index=i;button(row,"Abrir no visor "+(i+1)).setOnClickListener(v->select(index,p));}
        }
        select(0,first);if(second!=null)select(1,second);
    }
    private void select(int index,CameraOnvif.Profile profile){
        Pane pane=panes[index];pane.clear();
        pane.profile=profile;pane.title=profile.label;
        pane.photoButton.setVisibility(View.VISIBLE);
        int version=pane.generation,id=session;CameraOnvif client=camera;
        pane.note.setText(profile.label+" · solicitando vídeo…");
        worker.execute(()->{
            try{
                URI uri=client.stream(profile);
                runOnUiThread(()->{if(id==session && version==pane.generation){pane.stream=uri;pane.directUri=direct(client,profile,uri);pane.start();}});
            }catch(Exception e){runOnUiThread(()->{if(id==session && version==pane.generation){
                pane.note.setText(message(e));pane.directUri=direct(client,profile,null);
                if(pane.directUri!=null)pane.directButton.setVisibility(View.VISIBLE);
            }});}
        });
    }
    private URI direct(CameraOnvif client,CameraOnvif.Profile profile,URI uri){
        try{return client.directStream(profile,uri);}
        catch(IOException ignored){return null;}
    }
    private void stopSession(){
        ++session;
        if(camera!=null)camera.cancel();camera=null;
        for(Pane p:panes)if(p!=null)p.clear();
        options.removeAllViews();setInputs(true);status.setText("Desconectado.");
    }
    @Override protected void onStop(){stopSession();super.onStop();}
    @Override protected void onDestroy(){
        worker.shutdownNow();diagnostics.shutdownNow();
        for(Pane p:panes)if(p!=null){p.release();p.thread.quitSafely();}
        super.onDestroy();
    }

    private final class Pane implements SurfaceHolder.Callback {
        final SurfaceView view;
        final TextView note;
        final Button vlc, directButton, photoButton;
        final ImageView photo;
        CameraOnvif.Profile profile;
        URI directUri;
        boolean photos;
        Runnable nextPhoto;
        final HandlerThread thread;
        final Handler playback;
        // Only the playback thread creates, uses and releases this player.
        MediaPlayer player;
        URI stream;
        String title="";
        boolean ready, opening;
        volatile int generation;
        volatile int attempt;
        Runnable timer;
        Pane(int number){
            thread=new HandlerThread("vigia-visor-"+number);thread.start();
            playback=new Handler(thread.getLooper());
            label(root,"Visor "+number,19);note=label(root,"Sem vídeo",14);
            view=new SurfaceView(CameraLocal.this);root.addView(view,-1,dp(146));view.getHolder().addCallback(this);
            photo=new ImageView(CameraLocal.this);photo.setAdjustViewBounds(true);
            root.addView(photo,-1,-2);photo.setVisibility(View.GONE);
            photoButton=button(root,"Ver fotos ONVIF");photoButton.setVisibility(View.GONE);
            photoButton.setOnClickListener(v->{if(photos)stopPhotos(true);else startPhotos();});
            directButton=button(root,"Testar RTSP direto");directButton.setVisibility(View.GONE);
            directButton.setOnClickListener(v->{
                if(directUri==null)return;
                stopPhotos(false);photo.setVisibility(View.GONE);photo.setImageBitmap(null);
                release();stream=directUri;directUri=null;view.setVisibility(View.VISIBLE);
                title=profile.label+" (direto)";
                directButton.setVisibility(View.GONE);start();
            });
            vlc=button(root,"Abrir este perfil no VLC");
            vlc.setVisibility(View.GONE);
            vlc.setOnClickListener(v->{
                URI selected=stream;
                if(selected==null)return;
                Intent intent=new Intent(Intent.ACTION_VIEW);
                intent.setPackage("org.videolan.vlc");
                intent.setDataAndType(Uri.parse(DiagnosticoRtsp.enderecoSemUsuario(selected).toASCIIString()),"video/*");
                try{startActivity(intent);}
                catch(ActivityNotFoundException e){android.widget.Toast.makeText(CameraLocal.this,"Instale o VLC para Android para usar esse botão.",android.widget.Toast.LENGTH_LONG).show();}
            });
        }
        void clear(){
            ++generation;stream=null;profile=null;directUri=null;
            stopPhotos(false);release();
            photo.setImageBitmap(null);photo.setVisibility(View.GONE);view.setVisibility(View.VISIBLE);
            directButton.setVisibility(View.GONE);vlc.setVisibility(View.GONE);photoButton.setVisibility(View.GONE);
            note.setText("Sem vídeo");
        }
        void stopPhotos(boolean showStatus){
            if(photos)++generation;
            photos=false;
            if(nextPhoto!=null){main.removeCallbacks(nextPhoto);nextPhoto=null;}
            photoButton.setText("Ver fotos ONVIF");
            if(showStatus)note.setText(title+" · fotos pausadas");
        }
        void startPhotos(){
            if(camera==null || profile==null)return;
            ++generation;photos=true;stream=null;release();
            view.setVisibility(View.GONE);vlc.setVisibility(View.GONE);directButton.setVisibility(directUri==null?View.GONE:View.VISIBLE);
            photo.setImageBitmap(null);photo.setVisibility(View.VISIBLE);
            title=profile.label;photoButton.setText("Parar fotos");
            note.setText(title+" · solicitando foto ONVIF…");
            loadPhoto(camera,profile,generation);
        }
        void loadPhoto(CameraOnvif client,CameraOnvif.Profile selected,int version){
            worker.execute(()->{
                if(version!=generation)return;
                try{
                    byte[] data=client.snapshot(selected);
                    BitmapFactory.Options opts=new BitmapFactory.Options();opts.inJustDecodeBounds=true;
                    BitmapFactory.decodeByteArray(data,0,data.length,opts);
                    if(opts.outWidth<=0 || opts.outHeight<=0)throw new IOException("JPEG inválido.");
                    int sample=1;
                    while(Math.max(opts.outWidth,opts.outHeight)/sample>1600)sample*=2;
                    opts.inSampleSize=sample;opts.inJustDecodeBounds=false;
                    Bitmap bmp=BitmapFactory.decodeByteArray(data,0,data.length,opts);
                    if(bmp==null)throw new IOException("Falha ao abrir o JPEG.");
                    main.post(()->{
                        if(version!=generation){bmp.recycle();return;}
                        photo.setImageBitmap(bmp);
                        note.setText(selected.label+" · foto recebida às "+new java.text.SimpleDateFormat("HH:mm:ss",java.util.Locale.ROOT).format(new java.util.Date()));
                        nextPhoto=()->loadPhoto(client,selected,version);
                        main.postDelayed(nextPhoto,3000);
                    });
                }catch(Exception ex){
                    main.post(()->{if(version==generation){
                        stopPhotos(false);note.setText(selected.label+" · fotos interrompidas. "+message(ex));
                    }});
                }
            });
        }
        void release(){
            ++attempt;opening=false;
            if(timer!=null){main.removeCallbacks(timer);timer=null;}
            playback.post(()->{
                MediaPlayer old=player;player=null;
                if(old!=null){old.setOnErrorListener(null);old.setOnPreparedListener(null);old.setOnInfoListener(null);old.release();}
            });
        }
        void failed(int id,String detail){
            main.post(()->{
                if(id!=attempt || stream==null)return;
                release();
                int check=attempt;URI selected=stream;
                vlc.setVisibility(View.VISIBLE);
                if(directUri!=null)directButton.setVisibility(View.VISIBLE);
                String prefix=title+" · "+detail;
                note.setText(prefix+" Conferindo RTSP…");
                diagnostics.execute(()->{
                    if(check!=attempt)return;
                    String result=DiagnosticoRtsp.inspect(selected);
                    main.post(()->{if(check==attempt)note.setText(prefix+" "+result);});
                });
            });
        }
        void start(){
            if(!ready || stream==null || opening)return;
            opening=true;vlc.setVisibility(View.GONE);final int id=++attempt;String url=stream.toASCIIString();
            note.setText(title+" · abrindo RTSP…");
            timer=()->failed(id,"sem primeiro quadro em 25 s.");
            main.postDelayed(timer,25000);
            playback.post(()->{
                if(id!=attempt)return;
                try{
                    MediaPlayer mp=new MediaPlayer();player=mp;
                    mp.setDisplay(view.getHolder());mp.setVolume(0f,0f);
                    mp.setOnErrorListener((m,what,extra)->{failed(id,"falha RTSP/decodificação ("+what+", "+extra+").");return true;});
                    mp.setOnPreparedListener(m->{
                        if(id!=attempt)return;
                        try{m.start();}catch(IllegalStateException e){failed(id,"falha ao iniciar o vídeo.");return;}
                        main.post(()->{if(id==attempt)note.setText(title+" · aguardando imagem…");});
                    });
                    mp.setOnVideoSizeChangedListener((m,w,h)->main.post(()->{
                        if(id!=attempt || w<=0 || h<=0 || view.getWidth()<=0)return;
                        ViewGroup.LayoutParams lp=view.getLayoutParams();
                        lp.height=Math.max(1,Math.round(view.getWidth()*((float)h/w)));
                        view.setLayoutParams(lp);
                    }));
                    mp.setOnInfoListener((m,what,extra)->{
                        if(what==MediaPlayer.MEDIA_INFO_VIDEO_RENDERING_START)main.post(()->{
                            if(id==attempt){if(timer!=null)main.removeCallbacks(timer);note.setText(title+" · ao vivo");}
                        });
                        return false;
                    });
                    mp.setDataSource(url);if(id==attempt)mp.prepareAsync();
                }catch(Exception ex){failed(id,"o Android não conseguiu abrir este fluxo RTSP.");}
            });
        }
        @Override public void surfaceCreated(SurfaceHolder h){ready=true;start();}
        @Override public void surfaceChanged(SurfaceHolder h,int format,int w,int height){}
        @Override public void surfaceDestroyed(SurfaceHolder h){ready=false;release();}
    }
}
