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
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
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
    private final ExecutorService movement = Executors.newSingleThreadExecutor();
    private CameraOnvif control;
    private CameraOnvif.Profile controlProfile;
    private URI controlEndpoint;
    private boolean moving, stopRequired, light;
    private volatile int session;
    private LinearLayout loginForm, movementPanel, profilePanel;
    private CheckBox remember;
    private CameraLogin login;
    private Button theme, profilesToggle, gallery;
    private TextView motionNote;
    private final java.util.List<Button> arrows = new java.util.ArrayList<>();
    private Button halt;
    private int ink() { return light ? 0xff152627 : 0xfff1f5f5; }
    private int subtle() { return light ? 0xff45565d : 0xffbdc9d0; }
    private int background() { return light ? 0xfff3f6f6 : 0xff171b23; }

    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private final Handler main=new Handler();
    private final ExecutorService diagnostics=Executors.newFixedThreadPool(2);
    private final ExecutorService soundWorker=Executors.newSingleThreadExecutor();
    private Button clipButton;
    private TextView clipNote;
    private volatile boolean clipRequested,clipFinishing;
    private Button listenButton;
    private TextView soundNote;
    private URI soundUri;
    private volatile int soundVersion;
    private boolean listening;
    private CameraOnvif camera;
    private EditText address, user, password;
    private TextView status;
    private LinearLayout root, options;
    private Button connect;
    private final Pane[] panes=new Pane[2];


    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        ScrollView scroll=new ScrollView(this);
        root=new LinearLayout(this);root.setOrientation(1);
        int pad=dp(15);root.setPadding(pad,pad,pad,pad);scroll.addView(root);setContentView(scroll);
        light=getSharedPreferences("appearance",0).getBoolean("light",false);
        login=new CameraLogin(getSharedPreferences("camera-login",0));
        LinearLayout header=new LinearLayout(this);root.addView(header);
        TextView title=label(header,"Vigia",27);
        title.setLayoutParams(new LinearLayout.LayoutParams(0,-2,1));
        theme=button(header,"");
        theme.setOnClickListener(v->{
            light=!light;
            getSharedPreferences("appearance",0).edit().putBoolean("light",light).apply();
            applyTheme();
        });
        loginForm=column(root);
        loginForm.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS);
        label(loginForm,"Câmera no Wi-Fi",20);
        address=field("Endereço ONVIF","IP ou endereço da câmera",17);
        user=field("Usuário local","Usuário da câmera",1);user.setText("admin");
        password=field("Senha NVR/RTSP","Senha local da câmera",129);
        remember=new CheckBox(this);remember.setSaveEnabled(false);remember.setText("Lembrar login neste aparelho");loginForm.addView(remember);
        boolean lostLogin=false;
        try {
            String[] savedLogin=login.load();
            if(savedLogin!=null){
                address.setText(savedLogin[0]);user.setText(savedLogin[1]);password.setText(savedLogin[2]);
                remember.setChecked(true);
            }
        } catch(Exception e) {login.forget();lostLogin=true;}
        remember.setOnCheckedChangeListener((button,checked)->{if(!checked)login.forget();});
        connect=button(root,"Conectar à câmera");connect.setOnClickListener(v->{if(camera==null)begin();else disconnect();});
        status=label(root,lostLogin?"Informe novamente a senha para salvar o login.":"Conecte o celular ao Wi-Fi da câmera.",15);
        panes[0]=new Pane(1);
        movementPanel=column(root);
        label(movementPanel,"Mover câmera",19);
        LinearLayout row=new LinearLayout(this);movementPanel.addView(row);
        arrow(row,"←","Esquerda",-0.5,0);arrow(row,"↑","Cima",0,0.5);
        arrow(row,"↓","Baixo",0,-0.5);arrow(row,"→","Direita",0.5,0);
        halt=button(movementPanel,"Parar movimento");halt.setOnClickListener(v->move(0,0));
        motionNote=label(movementPanel,"",14);
        movementPanel.setVisibility(View.GONE);
        panes[1]=new Pane(2);
        profilesToggle=button(root,"Perfis de vídeo");
        profilePanel=column(root);options=profilePanel;
        profilesToggle.setOnClickListener(v->profilePanel.setVisibility(profilePanel.getVisibility()==View.VISIBLE?View.GONE:View.VISIBLE));
        profilePanel.setVisibility(View.GONE);profilesToggle.setVisibility(View.GONE);
        gallery=button(root,"Abrir vídeos do aparelho");
        gallery.setOnClickListener(v->startActivity(new Intent(this,Painel.class)));
        applyTheme();
    }

    private LinearLayout column(LinearLayout parent){
        LinearLayout group=new LinearLayout(this);group.setOrientation(1);parent.addView(group);return group;
    }

    private void applyTheme(){
        theme.setText(light?"Tema escuro":"Tema claro");
        root.setBackgroundColor(background());
        getWindow().setStatusBarColor(light?0xff45565d:background());
        getWindow().setNavigationBarColor(light?0xff45565d:background());
        tint(root);
    }

    private void tint(View view){
        if(view instanceof TextView){
            TextView text=(TextView)view;
            text.setTextColor(ink());
            if(text instanceof EditText){
                text.setHintTextColor(subtle());
                StateListDrawable backgrounds = new StateListDrawable();
                backgrounds.addState(new int[]{android.R.attr.state_focused}, fieldBackground(true));
                backgrounds.addState(new int[0], fieldBackground(false));
                text.setBackground(backgrounds);
                text.setPadding(dp(12),dp(8),dp(12),dp(8));
            }
            if(text instanceof Button && !(text instanceof CheckBox))
                text.setBackgroundTintList(android.content.res.ColorStateList.valueOf(light?0xffdce7e5:0xff36424d));
        }
        if(view instanceof ViewGroup){
            ViewGroup group=(ViewGroup)view;
            for(int i=0;i<group.getChildCount();i++)tint(group.getChildAt(i));
        }
    }

    private GradientDrawable fieldBackground(boolean focused){
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(light ? 0xffffffff : 0xff29323d);
        shape.setCornerRadius(dp(8));
        int border = focused ? (light ? 0xff236759 : 0xff9be4d0)
                             : (light ? 0xff78898b : 0xff70818a);
        shape.setStroke(dp(focused ? 2 : 1), border);
        return shape;
    }

    private void arrow(LinearLayout row,String text,String description,double x,double y){
        Button b=button(row,text);
        b.setContentDescription(description);
        b.setLayoutParams(new LinearLayout.LayoutParams(0,-2,1));
        b.setOnClickListener(v->move(x,y));
        arrows.add(b);
    }

    private void setupMovement(List<CameraOnvif.Profile> profiles){
        int id=session;
        CameraOnvif client;
        try {client=camera.controlClient();} catch(IOException e){return;}
        control=client;
        controlProfile=CameraOnvif.motionProfile(profiles);
        movement.execute(()->{
            try {
                if(id!=session)return;
                URI endpoint=client.motionEndpoint();
                main.post(()->{
                    if(id!=session)return;
                    controlEndpoint=endpoint;movementPanel.setVisibility(View.VISIBLE);
                    updateMovement();
                });
            } catch(Exception e) {
                main.post(()->{if(id==session)label(options,"Movimento indisponível nesta conexão.",14);});
            }
        });
    }

    private void updateMovement(){
        for(Button b:arrows)b.setEnabled(!moving && !stopRequired);
        halt.setEnabled(!moving);
    }

    private void move(double x,double y){
        if(moving || controlEndpoint==null)return;
        final int id=session;
        final URI endpoint=controlEndpoint;
        final CameraOnvif client=control;
        final CameraOnvif.Profile profile=controlProfile;
        moving=true;updateMovement();motionNote.setText("Enviando comando…");
        movement.execute(()->{
            if(id!=session)return;
            boolean moved=true, stopped=true;
            try {
                if(x!=0 || y!=0){
                    client.velocity(endpoint,profile,x,y);
                    Thread.sleep(300);
                }
            } catch(Exception e) {moved=false;}
            finally {
                try {client.stopMotion(endpoint,profile);} catch(Exception e){stopped=false;}
            }
            final boolean retry=!stopped;
            final String result=retry?"Parada sem confirmação. Toque em Parar movimento.":
                moved?"Parada confirmada.":"Movimento sem confirmação. Parada confirmada.";
            main.post(()->{
                if(id!=session)return;
                moving=false;stopRequired=retry;updateMovement();motionNote.setText(result);
            });
        });
    }
    private int dp(int x){return Math.round(x*getResources().getDisplayMetrics().density);}
    private TextView label(LinearLayout parent,String title,int size){
        TextView v=new TextView(this);v.setText(title);v.setTextColor(size>17?ink():subtle());v.setTextSize(size);
        v.setPadding(0,dp(5),0,dp(3));parent.addView(v);return v;
    }
    private EditText field(String title,String hint,int type){
        label(loginForm,title,14); EditText v=new EditText(this);v.setSingleLine(true);v.setInputType(type);v.setSaveEnabled(false);
        v.setHint(hint);v.setHintTextColor(subtle());v.setTextColor(ink());loginForm.addView(v);return v;
    }
    private Button button(LinearLayout parent,String title){
        Button b=new Button(this);b.setText(title);b.setAllCaps(false);parent.addView(b);tint(b);return b;
    }
    private void setInputs(boolean enabled){
        loginForm.setVisibility(enabled?View.VISIBLE:View.GONE);gallery.setVisibility(enabled?View.VISIBLE:View.GONE);
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
            if(p.name.equalsIgnoreCase("MainStream") && p.source.equals(first.source)){first=p;break;}
        }
        for(CameraOnvif.Profile p:list){
            if(!first.source.isEmpty() && !p.source.isEmpty() && !p.source.equals(first.source)){
                second=CameraOnvif.lightest(list,p.source);break;
            }
        }
        status.setText("Conectado à câmera");
        if(remember.isChecked()){
            try {login.save(address.getText().toString(),user.getText().toString(),password.getText().toString());}
            catch(Exception e){remember.setChecked(false);status.setText("Conectado. O aparelho não conseguiu salvar o login.");}
        }
        profilesToggle.setVisibility(View.VISIBLE);
        setupMovement(list);
        for(CameraOnvif.Profile p:list){
            label(options,p.label,15);
            LinearLayout row=new LinearLayout(this);options.addView(row);
            for(int i=0;i<2;i++){final int index=i;button(row,"Abrir no visor "+(i+1)).setOnClickListener(v->select(index,p));}
        }
        select(0,first);if(second!=null)select(1,second);
    }
    private void select(int index,CameraOnvif.Profile profile){
        if(index==0){setSoundSource(null);resetClip();}
        Pane pane=panes[index];pane.clear();pane.group.setVisibility(View.VISIBLE);
        pane.profile=profile;pane.title=profile.label;pane.useUdp=profile.name.equalsIgnoreCase("MainStream");
        pane.photoButton.setVisibility(View.VISIBLE);
        int version=pane.generation,id=session;CameraOnvif client=camera;
        pane.note.setText(profile.label+" · solicitando vídeo…");
        worker.execute(()->{
            try{
                URI uri=client.stream(profile);
                runOnUiThread(()->{if(id==session && version==pane.generation){pane.stream=uri;if(index==0 && pane.useUdp)setSoundSource(uri);pane.directUri=direct(client,profile,uri);pane.start();}});
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
    private void resetClip(){
        clipRequested=false;clipFinishing=false;clipButton.setVisibility(View.GONE);clipButton.setText("Gravar clipe");
        clipNote.setText("");
    }
    private void setSoundSource(URI uri){
        stopListening();soundUri=uri;
        listenButton.setVisibility(uri==null?View.GONE:View.VISIBLE);
    }
    private void stopListening(){
        ++soundVersion;listening=false;
        listenButton.setText("Ouvir");soundNote.setVisibility(View.GONE);
    }
    private void toggleListening(){
        if(listening){stopListening();return;}
        URI uri=soundUri;
        if(uri==null)return;
        final int version=++soundVersion;listening=true;
        listenButton.setText("Silenciar");soundNote.setText("Abrindo áudio por UDP…");soundNote.setVisibility(View.VISIBLE);
        soundWorker.execute(()->{
            if(version!=soundVersion)return;
            try(CameraSpeaker speaker=new CameraSpeaker(()->version==soundVersion,()->main.post(()->{
                if(version==soundVersion)soundNote.setText("Ouvindo a câmera");
            }))){
                new RtspUdp(uri).listen(speaker);
            }catch(Exception ex){
                main.post(()->{
                    if(version!=soundVersion)return;
                    stopListening();soundNote.setText("Escuta interrompida. "+soundError(ex));soundNote.setVisibility(View.VISIBLE);
                });
            }
        });
    }
    private String soundError(Exception e){
        String msg=e.getMessage();
        if(e.getClass()==IOException.class && msg!=null && msg.matches("(A câmera|O celular|A saída|PLAY|SETUP|OPTIONS|DESCRIBE|Sem par|Autenticação|Endereço).*"))return msg;
        return "Falha na conexão de áudio ou na saída de som.";
    }
    private void stopSession(){
        setSoundSource(null);
        resetClip();
        ++session;
        control=null;controlProfile=null;controlEndpoint=null;moving=false;stopRequired=false;
        movementPanel.setVisibility(View.GONE);motionNote.setText("");
        profilesToggle.setVisibility(View.GONE);profilePanel.setVisibility(View.GONE);
        if(camera!=null)camera.cancel();camera=null;
        for(Pane p:panes)if(p!=null){p.clear();p.group.setVisibility(View.GONE);}
        options.removeAllViews();setInputs(true);status.setText("Desconectado.");
    }
    private void disconnect(){
        stopSession();
        if(!remember.isChecked()){
            address.setText("");
            user.setText("admin");
            password.setText("");
        }
    }
    @Override protected void onStop(){disconnect();super.onStop();}
    @Override protected void onDestroy(){
        movement.shutdown();worker.shutdownNow();diagnostics.shutdownNow();soundWorker.shutdownNow();
        for(Pane p:panes)if(p!=null){p.release();p.thread.quitSafely();}
        super.onDestroy();
    }

    private final class Pane implements SurfaceHolder.Callback {
        final SurfaceView view;
        final TextView note;
        final Button vlc, directButton, photoButton, systemPlayer;
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
        boolean ready, opening, useUdp;
        volatile int generation;
        volatile int attempt;
        Runnable timer;
        final LinearLayout group;
        final boolean primary;
        Pane(int number){
            primary=number==1;
            group=column(root);group.setVisibility(View.GONE);
            thread=new HandlerThread("vigia-visor-"+number);thread.start();
            playback=new Handler(thread.getLooper());
            label(group,number==1?"Ao vivo":"Segundo visor",19);note=label(group,"Sem vídeo",14);
            view=new SurfaceView(CameraLocal.this);group.addView(view,-1,dp(146));view.getHolder().addCallback(this);
            photo=new ImageView(CameraLocal.this);photo.setAdjustViewBounds(true);
            group.addView(photo,-1,-2);photo.setVisibility(View.GONE);
            if(number==1){
                clipButton=button(group,"Gravar clipe");clipButton.setVisibility(View.GONE);
                clipNote=label(group,"",14);
                clipButton.setOnClickListener(v->{
                    clipRequested=!clipRequested;
                    clipButton.setText(clipRequested?"Encerrar clipe":"Gravar clipe");
                    clipNote.setText(clipRequested?"Aguardando quadro inicial…":"Finalizando clipe…");
                    if(!clipRequested){clipFinishing=true;clipButton.setEnabled(false);}
                });
                listenButton=button(group,"Ouvir");listenButton.setVisibility(View.GONE);
                listenButton.setOnClickListener(v->toggleListening());
                soundNote=label(group,"",14);soundNote.setVisibility(View.GONE);
            }
            photoButton=button(group,"Ver fotos ONVIF");photoButton.setVisibility(View.GONE);
            photoButton.setOnClickListener(v->{if(photos)stopPhotos(true);else startPhotos();});
            directButton=button(group,"Testar RTSP direto");directButton.setVisibility(View.GONE);
            directButton.setOnClickListener(v->{
                if(directUri==null)return;
                stopPhotos(false);photo.setVisibility(View.GONE);photo.setImageBitmap(null);
                release();useUdp=false;stream=directUri;directUri=null;view.setVisibility(View.VISIBLE);
                title=profile.label+" (direto)";
                directButton.setVisibility(View.GONE);start();
            });
            systemPlayer=button(group,"Tentar com o player do Android");systemPlayer.setVisibility(View.GONE);
            systemPlayer.setOnClickListener(v->{
                if(stream==null)return;
                release();useUdp=false;systemPlayer.setVisibility(View.GONE);start();
            });
            vlc=button(group,"Abrir este perfil no VLC");
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
            systemPlayer.setVisibility(View.GONE);++generation;stream=null;profile=null;directUri=null;
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
            systemPlayer.setVisibility(View.GONE);++generation;photos=true;stream=null;release();
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
            if(primary)resetClip();
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
            opening=true;systemPlayer.setVisibility(View.GONE);vlc.setVisibility(View.GONE);final int id=++attempt;String url=stream.toASCIIString();
            note.setText(title+" · abrindo RTSP…");
            timer=()->{
                if(useUdp)udpFailed(id,"Sem primeiro quadro decodificado em 25 s.");
                else failed(id,"sem primeiro quadro em 25 s.");
            };
            main.postDelayed(timer,25000);
            if(useUdp){
                URI selected=stream;int width=profile.width,height=profile.height;
                note.setText(title+" · abrindo vídeo por UDP…");
                playback.post(()->playUdp(id,selected,width,height));
                return;
            }
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
        void playUdp(int id,URI selected,int width,int height){
            if(id!=attempt)return;
            UdpDecoder.View callbacks=new UdpDecoder.View(){
                public boolean active(){return id==attempt;}
                public boolean wantsClip(){return primary && active() && clipRequested;}
                public boolean finishingClip(){return primary && active() && clipFinishing;}
                public void recording(boolean recording,String detail){main.post(()->{
                    if(!active() || !primary)return;
                    if(!recording){clipFinishing=false;clipRequested=false;clipButton.setEnabled(true);clipButton.setText("Gravar clipe");}
                    clipNote.setText(detail);
                });}
                public void size(int w,int h){main.post(()->{
                    if(!active() || w<=0 || h<=0 || view.getWidth()==0)return;
                    ViewGroup.LayoutParams lp=view.getLayoutParams();
                    lp.height=Math.max(1,Math.round(view.getWidth()*((float)h/w)));view.setLayoutParams(lp);
                });}
                public void firstFrame(){main.post(()->{
                    if(!active())return;
                    if(timer!=null)main.removeCallbacks(timer);
                    note.setText(title+" · ao vivo por UDP");
                    if(primary){clipButton.setVisibility(View.VISIBLE);clipButton.setEnabled(true);}

                });}
            };
            try(UdpDecoder decoder=new UdpDecoder(CameraLocal.this,view.getHolder().getSurface(),width,height,callbacks)){
                new RtspUdp(selected).play(decoder);
            }catch(Exception ex){
                String reason=ex instanceof java.net.SocketTimeoutException?"Tempo esgotado na negociação RTSP.":
                    ex instanceof IOException && ex.getClass()==IOException.class && ex.getMessage()!=null &&
                    ex.getMessage().matches("(OPTIONS|DESCRIBE|SETUP|PLAY|A câmera|O Android|Quadro maior|Sem par|Autenticação|Endereço|Conexão).*")?
                    ex.getMessage():"Falha ao receber ou decodificar o vídeo UDP.";
                main.post(()->udpFailed(id,reason));
            }
        }
        void udpFailed(int id,String reason){
            if(id!=attempt)return;
            release();note.setText(title+" · "+reason);
            systemPlayer.setVisibility(View.VISIBLE);vlc.setVisibility(View.VISIBLE);
            if(directUri!=null)directButton.setVisibility(View.VISIBLE);
        }
        @Override public void surfaceCreated(SurfaceHolder h){ready=true;start();}
        @Override public void surfaceChanged(SurfaceHolder h,int format,int w,int height){}
        @Override public void surfaceDestroyed(SurfaceHolder h){ready=false;release();}
    }
}
