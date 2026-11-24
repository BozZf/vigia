# Vigia para Android

Prévia 0.1.0 do painel de câmera com duas lentes. Reproduz dois vídeos de demonstração em paralelo ou dois vídeos escolhidos no aparelho. O painel oferece temas claro e escuro e pausa a reprodução quando o usuário sai. A reprodução dos dois vídeos de demonstração foi confirmada em um Samsung Galaxy A40.

## Executar

Abra esta pasta no Android Studio com o SDK Android 35, JDK 17 e Gradle 8.9. Sincronize o projeto, escolha o módulo `app` e execute em um aparelho com Android 8.0 ou posterior. Na tela inicial, toque em **Reproduzir teste**.

## Verificar os controles

Na pasta do projeto, execute `node tests/painel.cjs` para testar a seleção dos arquivos, a pausa, a troca de tema e a recuperação de erros de reprodução.

## Integração com a câmera

O login Yoosee e a transmissão ao vivo estão em desenvolvimento. Esta versão reproduz mídia local e não solicita credenciais.
