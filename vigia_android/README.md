# Vigia para Android

A versão 0.2.2 inclui o teste local ONVIF/RTSP. Reproduz dois vídeos de demonstração em paralelo ou dois vídeos escolhidos no aparelho. O painel oferece temas claro e escuro e pausa a reprodução quando o usuário sai. A reprodução dos dois vídeos de demonstração foi confirmada em um Samsung Galaxy A40.

## Executar

Abra esta pasta no Android Studio com o SDK Android 35, JDK 17 e Gradle 8.9. Sincronize o projeto, escolha o módulo `app` e execute em um aparelho com Android 8.0 ou posterior. Na tela inicial, toque em **Testar câmera no Wi-Fi**. Para conferir os vídeos de demonstração, use **Reproduzir teste**.

## Testar a câmera no Wi-Fi

Conecte o celular à rede da câmera e informe seu IPv4 local. O app aceita o endereço do serviço ONVIF que aparece no ONVIF Device Manager, inclusive a porta e o caminho. Com apenas o IP, usa a porta 5000. Preencha o usuário e a senha locais NVR/RTSP. A tela também aceita campos vazios para dispositivos que oferecem acesso local sem usuário. A senha permanece na memória enquanto a tela está aberta.

Ao conectar, o app consulta o relógio, o serviço de mídia ONVIF Media1 e os perfis de vídeo. A reprodução começa pelo perfil de menor resolução conhecida da primeira fonte. Quando há outra fonte identificada, abre seu perfil mais leve no segundo visor. Uma câmera também pode enviar as duas imagens juntas no mesmo fluxo. Os botões de perfil permitem escolher o que testar em cada visor. O estado “ao vivo” exige a indicação de primeiro quadro renderizado pelo player do Android. Se o player falhar, o Vigia consulta a descrição RTSP do perfil e exibe a resposta. Um código 200 confirma a descrição do fluxo. A exibição da imagem depende também do transporte de mídia e do decodificador. O botão **Abrir este perfil no VLC** entrega o endereço ao VLC instalado. Caso o VLC peça autenticação, informe o usuário e a senha locais. Ao sair da tela, o app encerra os players e as consultas. Este teste requer que o equipamento disponibilize vídeo na rede local.

### Se a câmera responder RTSP 400

O Vigia mostra em qual porta e etapa a câmera recusou a consulta de descrição do vídeo. **Testar RTSP direto** abre um caminho alternativo usual da família Yoosee na mesma câmera, com as credenciais locais já informadas. Esse botão aparece para MainStream ou SubStream quando o destino alternativo difere do endereço anunciado, ou quando a câmera não fornece um endereço. A compatibilidade depende do firmware.

**Ver fotos ONVIF** solicita ao serviço de mídia o JPEG do perfil escolhido. Se a câmera oferecer essa função, a tela mostra a hora de recebimento e pede a próxima foto três segundos depois. **Parar fotos** pausa as atualizações. A troca de perfil e a saída da tela também encerram esse modo. As fotos ficam na memória durante a visualização. Para conferir as lentes em uma imagem maior, selecione o perfil MainStream.

## Verificar os controles

Na pasta do projeto, execute `node tests/painel.cjs` para testar a seleção dos arquivos, a pausa, a troca de tema e a recuperação de erros de reprodução.

## Integração com a câmera

O teste de Wi-Fi usa o serviço da própria câmera. A reprodução dos fluxos reais da câmera no Galaxy A40 ainda depende do teste no equipamento. O histórico abaixo registra a investigação da integração de conta separada.

### O que já foi identificado no SDK Android

Na implementação pública analisada, `emailLogin` delega a `mobileLogin`. Esse método solicita `CreateUsrToken` com o identificador de acesso, o identificador da instalação e o prazo de validade. A senha e o e-mail informados na tela não participam dessa solicitação. A lista de câmeras vem de `DescribeBindDev` para o mesmo identificador de acesso. Esse fluxo pressupõe acesso ao serviço IoT Video da Tencent e não demonstra como entrar com uma conta de consumidor Yoosee já existente. [Implementação do serviço de conta](https://github.com/GWTimes/IoTVideo-Android/blob/0e8ae768843018f7d46194f715f9bd46f4a79fb6/accountmgrtc/src/main/java/com/tencentcs/iotvideo/http/TencentcsHttpServiceAdapter.java)

O projeto GwellDemo também descreve uma integração Android na qual a Gwell fornece os dados de aplicativo para o nome de pacote registrado. Para usar essa via no Vigia, falta confirmar qual versão atende às câmeras de duas lentes com ID de dez dígitos e se ela dá acesso aos dispositivos que o usuário já vinculou no Yoosee. [Integração do GwellDemo](https://github.com/jwkj/GwellDemo#readme)

O visualizador do exemplo associa um dispositivo e um identificador de fonte a cada painel. Esse identificador chega ao reprodutor em `setDataResource(deviceId, definition, sourceId)`. Para validar a integração no A40, o primeiro teste precisa listar a câmera já vinculada à conta. Em seguida, é preciso confirmar que os dois identificadores de fonte entregam as cenas distintas da lente superior e da inferior. [Seleção de fontes](https://github.com/GWTimes/IoTVideo-Android/blob/0e8ae768843018f7d46194f715f9bd46f4a79fb6/app/src/main/java/com/tencentcs/iotvideodemo/videoplayer/MultiMonitorPlayerActivity.java) · [Reprodutor](https://github.com/GWTimes/IoTVideo-Android/blob/0e8ae768843018f7d46194f715f9bd46f4a79fb6/app/src/main/java/com/tencentcs/iotvideodemo/videoplayer/monitor/IoTMonitorPlayerOwner.java)
