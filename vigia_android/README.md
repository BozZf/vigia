# Vigia para Android

A versão 0.3.3 abre diretamente a câmera local na rede Wi-Fi. Reproduz dois vídeos de demonstração em paralelo ou dois vídeos escolhidos no aparelho. O painel oferece temas claro e escuro e pausa a reprodução quando o usuário sai. A reprodução dos dois vídeos de demonstração foi confirmada em um Samsung Galaxy A40.

## Executar

Abra esta pasta no Android Studio com o SDK Android 35, JDK 17 e Gradle 8.9. Sincronize o projeto, escolha o módulo `app` e execute em um aparelho com Android 8.0 ou posterior. Na tela inicial, informe a conexão e toque em **Conectar à câmera**. **Abrir vídeos do aparelho** leva ao painel de arquivos e demonstrações.

## Testar a câmera no Wi-Fi

Conecte o celular à rede da câmera e informe seu IPv4 local. O app aceita o endereço do serviço ONVIF que aparece no ONVIF Device Manager, inclusive a porta e o caminho. Com apenas o IP, usa a porta 5000. Preencha o usuário e a senha locais NVR/RTSP. A tela também aceita campos vazios para dispositivos que oferecem acesso local sem usuário. Marque **Lembrar login neste aparelho** para salvar a conexão após a autenticação. O Vigia cifra a senha com uma chave AES-GCM do Android Keystore. Desmarcar a opção remove a conexão salva. Com a opção desmarcada, desconectar ou sair da tela limpa o endereço e a senha e repõe o usuário padrão (admin). Uma falha de conexão mantém os campos disponíveis para correção.

Ao conectar, o app consulta o relógio, o serviço de mídia ONVIF Media1 e os perfis de vídeo. O app abre o MainStream quando ele está presente na primeira fonte e usa seu endereço ONVIF para negociar uma única faixa de vídeo por RTP/UDP. Recebe H.264 ou H.265 e envia os quadros ao MediaCodec do Android. A imagem composta das duas lentes ocupa um único visor. O PC confirmou as duas cenas no MainStream por UDP. O Galaxy A40 exibiu as duas cenas no Visor 1 com o estado “ao vivo por UDP”. Se faltar MainStream, o app escolhe o perfil mais leve da primeira fonte. Quando há outra fonte identificada, abre seu perfil mais leve no segundo visor. Os botões de perfil permitem trocar a seleção. Se a reprodução UDP falhar, **Tentar com o player do Android** usa o reprodutor padrão para o mesmo endereço. O botão **Abrir este perfil no VLC** entrega o endereço ao VLC instalado. Caso o VLC peça autenticação, informe o usuário e a senha locais. Ao sair da tela, o app encerra os players e as consultas. Este teste requer que o equipamento disponibilize vídeo na rede local.

### Movimento e gravação local

As quatro setas dão passos curtos na lente móvel. O app solicita a parada por velocidade zero após cada passo, inclusive se a resposta de movimento se perder. O botão **Parar movimento** permite repetir o pedido. O teste no PC confirmou esse comportamento na A29. Os controles aparecem quando a câmera anuncia o serviço PTZ.

Durante o vídeo UDP no primeiro visor, **Gravar clipe** salva as duas lentes do MainStream e o áudio da câmera em um MP4. O app busca a faixa de áudio e inicia o clipe em um quadro-chave de vídeo. Se o áudio estiver indisponível na abertura, a tela indica que está gravando só vídeo. **Ouvir** e **Silenciar** controlam o som no alto-falante do celular durante a gravação. Toque em **Encerrar clipe** para finalizar. Sair da tela também encerra o clipe. No Android 10 ou superior, os clipes aparecem em Filmes/Vigia na galeria. Nas versões 8 e 9, ficam na pasta externa do app em Android/data/br.vigia.mobile/files/Movies.

### Ouvir a câmera

Com o MainStream selecionado no Visor 1, **Ouvir** abre a faixa mono G.711 A-law por UDP em uma sessão RTSP de áudio. A escuta inicia desligada. **Silenciar**, trocar o perfil do Visor 1, desconectar ou sair da tela encerram a escuta. Use o volume de mídia do aparelho. O teste no PC recebeu seis segundos de PCMA a 16 kHz. A escuta foi confirmada no A40.

### Se a câmera responder RTSP 400

O Vigia mostra em qual porta e etapa a câmera recusou a consulta de descrição do vídeo. **Testar RTSP direto** abre um caminho alternativo usual da família Yoosee na mesma câmera, com as credenciais locais já informadas. Esse botão aparece para MainStream ou SubStream quando o destino alternativo difere do endereço anunciado, ou quando a câmera não fornece um endereço. A compatibilidade depende do firmware.

**Ver fotos ONVIF** solicita ao serviço de mídia o JPEG do perfil escolhido. Se a câmera oferecer essa função, a tela mostra a hora de recebimento e pede a próxima foto três segundos depois. **Parar fotos** pausa as atualizações. A troca de perfil e a saída da tela também encerram esse modo. Se a conexão cair antes de completar uma resposta, o app solicita um novo endereço e tenta mais uma vez. O visor identifica se a falha ocorreu ao pedir o endereço ou ao baixar a foto. As fotos ficam na memória durante a visualização. Para conferir as lentes em uma imagem maior, selecione o perfil MainStream.

## Verificar os controles

Na pasta do projeto, execute `node tests/painel.cjs` para testar a seleção dos arquivos, a pausa, a troca de tema e a recuperação de erros de reprodução.

## Integração com a câmera

O teste de Wi-Fi usa o serviço da própria câmera. Os testes no A40 confirmaram a exibição das duas lentes no MainStream. O teste da versão 0.3.0 no A40 confirmou a escuta e o movimento nas quatro direções. O clipe enviado mostra as duas lentes. Na versão 0.3.2, o arquivo de teste continha áudio AAC e pausas entre imagens. A 0.3.3 recebe pacotes UDP em paralelo à gravação e aguarda rajadas de áudio atrasadas. A fluidez precisa ser conferida no A40. O histórico abaixo registra a investigação da integração de conta separada.

### O que já foi identificado no SDK Android

Na implementação pública analisada, `emailLogin` delega a `mobileLogin`. Esse método solicita `CreateUsrToken` com o identificador de acesso, o identificador da instalação e o prazo de validade. A senha e o e-mail informados na tela não participam dessa solicitação. A lista de câmeras vem de `DescribeBindDev` para o mesmo identificador de acesso. Esse fluxo pressupõe acesso ao serviço IoT Video da Tencent e não demonstra como entrar com uma conta de consumidor Yoosee já existente. [Implementação do serviço de conta](https://github.com/GWTimes/IoTVideo-Android/blob/0e8ae768843018f7d46194f715f9bd46f4a79fb6/accountmgrtc/src/main/java/com/tencentcs/iotvideo/http/TencentcsHttpServiceAdapter.java)

O projeto GwellDemo também descreve uma integração Android na qual a Gwell fornece os dados de aplicativo para o nome de pacote registrado. Para usar essa via no Vigia, falta confirmar qual versão atende às câmeras de duas lentes com ID de dez dígitos e se ela dá acesso aos dispositivos que o usuário já vinculou no Yoosee. [Integração do GwellDemo](https://github.com/jwkj/GwellDemo#readme)

O visualizador do exemplo associa um dispositivo e um identificador de fonte a cada painel. Esse identificador chega ao reprodutor em `setDataResource(deviceId, definition, sourceId)`. Para validar a integração no A40, o primeiro teste precisa listar a câmera já vinculada à conta. Em seguida, é preciso confirmar que os dois identificadores de fonte entregam as cenas distintas da lente superior e da inferior. [Seleção de fontes](https://github.com/GWTimes/IoTVideo-Android/blob/0e8ae768843018f7d46194f715f9bd46f4a79fb6/app/src/main/java/com/tencentcs/iotvideodemo/videoplayer/MultiMonitorPlayerActivity.java) · [Reprodutor](https://github.com/GWTimes/IoTVideo-Android/blob/0e8ae768843018f7d46194f715f9bd46f4a79fb6/app/src/main/java/com/tencentcs/iotvideodemo/videoplayer/monitor/IoTMonitorPlayerOwner.java)
