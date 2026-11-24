# Vigia para Android

Prévia 0.1.0 do painel de câmera com duas lentes. Reproduz dois vídeos de demonstração em paralelo ou dois vídeos escolhidos no aparelho. O painel oferece temas claro e escuro e pausa a reprodução quando o usuário sai. A reprodução dos dois vídeos de demonstração foi confirmada em um Samsung Galaxy A40.

## Executar

Abra esta pasta no Android Studio com o SDK Android 35, JDK 17 e Gradle 8.9. Sincronize o projeto, escolha o módulo `app` e execute em um aparelho com Android 8.0 ou posterior. Na tela inicial, toque em **Reproduzir teste**.

## Verificar os controles

Na pasta do projeto, execute `node tests/painel.cjs` para testar a seleção dos arquivos, a pausa, a troca de tema e a recuperação de erros de reprodução.

## Integração com a câmera

O login Yoosee e a transmissão ao vivo estão em desenvolvimento. Esta versão reproduz mídia local e não solicita credenciais.

### O que já foi identificado no SDK Android

O exemplo da Gwell inicializa o serviço de conta com o identificador do produto e do pacote Android. O login por e-mail ou telefone retorna um identificador de acesso e um token de sessão. O serviço de conta também expõe a lista de dispositivos. A compatibilidade desse login com uma conta de varejo Yoosee e com as câmeras já vinculadas a ela ainda precisa de confirmação. [Inicialização](https://github.com/GWTimes/IoTVideo-Android/blob/0e8ae768843018f7d46194f715f9bd46f4a79fb6/app/src/main/java/com/tencentcs/iotvideodemo/DemoApp.kt) · [Login](https://github.com/GWTimes/IoTVideo-Android/blob/0e8ae768843018f7d46194f715f9bd46f4a79fb6/app/src/main/java/com/tencentcs/iotvideodemo/accountmgr/login/LoginManager.java) · [Serviço de conta](https://github.com/GWTimes/IoTVideo-Android/blob/0e8ae768843018f7d46194f715f9bd46f4a79fb6/accountmgrtc/src/main/java/com/tencentcs/iotvideo/accountmgr/HttpService.java)

O visualizador do exemplo associa um dispositivo e um identificador de fonte a cada painel. Esse identificador chega ao reprodutor em `setDataResource(deviceId, definition, sourceId)`. Para validar a integração no A40, o primeiro teste precisa listar a câmera já vinculada à conta. Em seguida, é preciso confirmar que os dois identificadores de fonte entregam as cenas distintas da lente superior e da inferior. [Seleção de fontes](https://github.com/GWTimes/IoTVideo-Android/blob/0e8ae768843018f7d46194f715f9bd46f4a79fb6/app/src/main/java/com/tencentcs/iotvideodemo/videoplayer/MultiMonitorPlayerActivity.java) · [Reprodutor](https://github.com/GWTimes/IoTVideo-Android/blob/0e8ae768843018f7d46194f715f9bd46f4a79fb6/app/src/main/java/com/tencentcs/iotvideodemo/videoplayer/monitor/IoTMonitorPlayerOwner.java)
