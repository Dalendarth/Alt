# Alt — instruções do projeto

Ferramenta de print anotado para Windows, de uso pessoal do Guilherme. Nasceu de um
problema real durante a escrita do manual do Fieldly: anotar prints com seta,
callout e marcador sem ferramenta decente para isso.

O código é **um arquivo**, `alt.py`. Não quebre em módulos sem pedido.

## O escopo é fechado de propósito

Quatro formas, e só quatro: **seta**, **callout redondo**, **marcador retangular de
contorno**, **etiqueta de texto de fundo preenchido**.

A razão de existir é justamente não ser um TechSmith: as ferramentas do gênero fazem
trinta coisas. **Não acrescente forma, filtro, borrão, numeração automática de
sequência nem exportação nova sem o Guilherme pedir.** Se parecer que falta algo,
pergunte antes de escrever.

A paleta é a mesma do manual do Fieldly e não muda por conta própria:

| Cor | Hex |
|---|---|
| Magenta (padrão) | `#C93466` |
| Laranja | `#F8A113` |
| Verde | `#7EBE1A` |
| Navy | `#475279` |

## Decisões que parecem erradas e não são

Estas custaram depuração. Não as desfaça sem entender o motivo.

**O Print Screen é ouvido por `WH_KEYBOARD_LL`, não por `RegisterHotKey`.** Para essa
tecla o `RegisterHotKey` aceita o registro e devolve sucesso, mas o evento nunca
chega: antivírus, OneDrive e a captura do próprio Windows têm gancho de baixo nível e
consomem a tecla antes do despachante de atalhos. **Registro não é entrega.** O
`RegisterHotKey` ficou só como reserva, e nesse caso o `WM_HOTKEY` tem de estar no
dicionário do `lpfnWndProc` — faltar ele já foi bug.

**A referência do callback do gancho tem de ficar viva** (`self._callback`). Se o
Python coletar o objeto, o Windows chama memória liberada e o processo morre sem
aviso.

**A bandeja e o gancho moram no mesmo fio.** Os dois dependem do mesmo laço de
mensagens do Windows. Nada de `tkinter` nesse fio: os avisos vão para uma fila e o
fio principal consome.

**A caixa da etiqueta de texto é medida pelo maior entre a métrica do Pillow e a do
tkinter.** O Pillow desenha o arquivo e o tkinter desenha o editor; medir por um só
corta o texto no outro.

**As formas vivem em coordenadas de imagem, não de tela, e o arquivo final é
desenhado pelo Pillow**, nunca capturando o canvas. É o que garante resolução cheia
quando o editor exibe reduzido.

**O executável é montado em pasta (`--onedir`), não em arquivo único.** Arquivo único
se autodescompacta no `%TEMP%` a cada abertura, e a heurística do Kaspersky — que o
Guilherme tem instalado — marca esse comportamento. O Kaspersky também bloqueia o
`Alt.vbs` aberto pelo Explorer; foi por isso que o executável passou a existir.

**Os `--hidden-import` do build são obrigatórios.** `win32clipboard`, `win32api`,
`win32con` e `win32gui` são importados dentro de função, e a análise estática do
PyInstaller não os encontra.

## Como verificar sem poder clicar

Claude não consegue clicar numa interface. Então a verificação é por outro caminho, e
ele já existe:

```
python alt.py --autoteste
```

Confere DPI, captura em multi-monitor, área de transferência, **dispara uma tecla
sintética e confirma que o `Ctrl + Print Screen` chega de fato**, e salva uma amostra
das quatro formas para conferência visual.

Ao mexer no desenho, o padrão é este: gerar a forma, renderizar com o Pillow e
**medir por pixel**. Foi assim que se provou que o texto nunca estoura a borda da
etiqueta — 14 px de folga mínima em dez casos, incluindo descendentes, caixa-alta
larga, três linhas e acentuação. Não confie em inspeção visual para requisito de
geometria.

Antes de dar qualquer coisa como pronta, rode também o teste de montagem: construir
`Editor` e `SelecaoDeArea` com imagens pequenas e destruir, para pegar erro de
montagem sem depender de clique.

## Build

```
build.cmd
```

Gera `Programa\Alt.exe`, organiza a saída e roda o autoteste. A pasta `Programa` não
é versionada: são 45 MB em mais de mil arquivos. Para distribuir o executável, use
Releases do GitHub, não commit do binário.

## Uma instância por vez

Só um processo pode ter o gancho. Se o atalho parar de responder, quase sempre há
outra instância rodando — encerre pela bandeja antes de abrir de novo. Ao testar,
encerre o `Alt.exe` antes de recompilar, senão o build não consegue substituir os
arquivos.

## Relação com o outro projeto

O manual do Fieldly é **outro projeto**, em
`C:\Users\Guilherme\Documents\BSIT\fieldly-playwright`, com contexto e memória
próprios. Aqui só interessa que a paleta é compartilhada e que o Alt foi feito para
anotar aqueles prints. **Não traga assunto de documentação para cá** — nem regra de
negócio do Fieldly, nem entrega de `.docx`, nem Jira.
