# Vigia para Windows

A versão 0.5.1 reúne as duas lentes da câmera Yoosee em um painel com comandos de luz, movimento, áudio e interfone. As gravações podem ser enviadas ao Google Drive ou a uma pasta sincronizada.

## Abrir o aplicativo

1. Instale o cliente Yoosee 1.0.0.14 para Windows e o Python 3.11 ou posterior de 64 bits com Tkinter.
2. Baixe a branch `main` pelo botão **Code → Download ZIP** e extraia a pasta inteira.
3. Abra `INICIAR.cmd`. Se o painel solicitar, selecione o arquivo `Yoosee.exe` da instalação oficial.

O adaptador compilado acompanha o projeto. Para recompilá-lo, execute `COMPILAR.cmd` no prompt de ferramentas nativas x64 do Visual Studio. As instruções sobre gravação diária, retenção e configuração do Drive estão em [LEIA_PRIMEIRO.txt](LEIA_PRIMEIRO.txt).

## Android

O aplicativo para celular está na [branch android](https://github.com/BozZf/vigia/tree/android/vigia_android).

## Testes

Execute `py -m unittest discover -s tests` a partir da raiz do projeto.
