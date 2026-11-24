# Vigia para Android

Prévia 0.1.0 do painel de câmera com duas lentes. Reproduz dois vídeos de demonstração em paralelo ou dois vídeos escolhidos no aparelho. O painel oferece temas claro e escuro e pausa a reprodução quando o usuário sai. A reprodução dos dois vídeos de demonstração foi confirmada em um Samsung Galaxy A40.

## Executar

Abra esta pasta no Android Studio com o SDK Android 35, JDK 17 e Gradle 8.9. Sincronize o projeto, escolha o módulo `app` e execute em um aparelho com Android 8.0 ou posterior. Na tela inicial, toque em **Reproduzir teste**.

## Verificar os controles

Na pasta do projeto, execute `node tests/painel.cjs` para testar a seleção dos arquivos, a pausa, a troca de tema e a recuperação de erros de reprodução.

## Integração com a câmera

O login Yoosee e a transmissão ao vivo estão em desenvolvimento. Esta versão reproduz mídia local e não solicita credenciais.

### O que já foi identificado no SDK Android

Na implementação pública analisada, `emailLogin` delega a `mobileLogin`. Esse método solicita `CreateUsrToken` com o identificador de acesso, o identificador da instalação e o prazo de validade. A senha e o e-mail informados na tela não participam dessa solicitação. A lista de câmeras vem de `DescribeBindDev` para o mesmo identificador de acesso. Esse fluxo pressupõe acesso ao serviço IoT Video da Tencent e não demonstra como entrar com uma conta de consumidor Yoosee já existente. [Implementação do serviço de conta](https://github.com/GWTimes/IoTVideo-Android/blob/0e8ae768843018f7d46194f715f9bd46f4a79fb6/accountmgrtc/src/main/java/com/tencentcs/iotvideo/http/TencentcsHttpServiceAdapter.java)

O projeto GwellDemo também descreve uma integração Android na qual a Gwell fornece os dados de aplicativo para o nome de pacote registrado. Para usar essa via no Vigia, falta confirmar qual versão atende às câmeras de duas lentes com ID de dez dígitos e se ela dá acesso aos dispositivos que o usuário já vinculou no Yoosee. [Integração do GwellDemo](https://github.com/jwkj/GwellDemo#readme)

O visualizador do exemplo associa um dispositivo e um identificador de fonte a cada painel. Esse identificador chega ao reprodutor em `setDataResource(deviceId, definition, sourceId)`. Para validar a integração no A40, o primeiro teste precisa listar a câmera já vinculada à conta. Em seguida, é preciso confirmar que os dois identificadores de fonte entregam as cenas distintas da lente superior e da inferior. [Seleção de fontes](https://github.com/GWTimes/IoTVideo-Android/blob/0e8ae768843018f7d46194f715f9bd46f4a79fb6/app/src/main/java/com/tencentcs/iotvideodemo/videoplayer/MultiMonitorPlayerActivity.java) · [Reprodutor](https://github.com/GWTimes/IoTVideo-Android/blob/0e8ae768843018f7d46194f715f9bd46f4a79fb6/app/src/main/java/com/tencentcs/iotvideodemo/videoplayer/monitor/IoTMonitorPlayerOwner.java)
