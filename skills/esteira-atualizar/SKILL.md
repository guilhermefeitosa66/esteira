---
name: esteira-atualizar
description: >
  Atualiza a esteira instalada no projeto com o que saiu de novo no repositório dela no GitHub, sem
  perder as melhorias que o próprio projeto fez nas skills e nos scripts: compara o commit instalado
  (.claude/esteira-versao.json) com a main, faz o merge de 3 vias de cada arquivo, resolve os
  conflitos preservando as duas intenções e grava a nova versão. Use quando o usuário chamar
  /esteira-atualizar ou pedir para "atualizar a esteira", "ver se tem versão nova da esteira",
  "trazer as melhorias da esteira".
---

# Atualizar a esteira

Você traz para este projeto as melhorias da esteira **sem desfazer as do projeto**. As skills e os
scripts daqui podem ter sido ajustados por quem usa: esses ajustes são tão importantes quanto as
novidades do repositório. Aqui você conversa com o usuário, em português.

```bash
A=.claude/skills/esteira-atualizar/scripts/atualizar.py
```

## 1. Tem atualização?

```bash
python3 $A check
```

- `atualizado: true`: diga que a esteira está na última versão (commit curto e data) e pare.
- `sem_arquivo_de_versao: true`: instalação de antes do controle de versão. Siga mesmo assim: o
  `prepare` estima a base (o commit da main mais parecido com os arquivos daqui). Avise que é uma
  estimativa e que, daqui em diante, a versão fica gravada.
- Erro de rede ou de acesso: mostre o erro e pare.

## 2. Preparar

```bash
python3 $A prepare
```

Nada no projeto é tocado ainda. O script clona a main num diretório de trabalho (`work`) e, para
cada arquivo da esteira, compara base (o commit instalado), local (o projeto) e novo (a main). Em
`work/resultado/` fica o **estado final** de cada arquivo da lista; arquivo ausente ali significa
que será apagado. As ações:

| Ação | O que é | O que fazer |
|---|---|---|
| `atualizar`, `adicionar`, `remover` | o projeto não mexeu no arquivo: vem o do repositório | nada |
| `mesclado` | os dois mudaram, em trechos diferentes: o `git merge-file` juntou | conferir por amostragem |
| `conflito` | os dois mudaram o mesmo trecho: `resultado/` tem as marcas | resolver (passo 3) |
| `decidir:mudou-aqui-apagado-no-repositorio` | por padrão o arquivo fica | decidir (passo 3) |
| `decidir:apagado-aqui-mudou-no-repositorio` | por padrão continua apagado | decidir (passo 3) |

Arquivo que só o projeto mudou, ou que só existe no projeto, nem aparece: fica como está. O
`config.json` e os `hooks/` de `.claude/esteira/` nunca entram.

Mostre ao usuário, curto: de qual versão para qual (`base` → `novo`), os `commits_novos` e quantos
arquivos em cada ação. Para entender **o que** mudou e **por quê**, leia o `diff_do_repositorio`
junto com as mensagens dos commits.

## 3. Resolver os pendentes

Para cada arquivo em `pendentes`, as três versões estão em `work/conflitos/<arquivo>.{base,local,novo}`.

**Conflito.** O arquivo em `work/resultado/` tem blocos assim:

```
<<<<<<< local
(como o projeto deixou)
||||||| base
(como era na versão instalada)
=======
(como está na main)
>>>>>>> novo
```

Compare cada lado com a base para entender as duas intenções: o que o projeto quis com o ajuste
dele e o que a melhoria do repositório traz. Reescreva o trecho **combinando as duas**: a melhoria
do repositório entra e o ajuste do projeto continua valendo. Edite o arquivo em `resultado/` (nunca o
do projeto) e tire todas as marcas.

- Não descarte em silêncio a mudança do projeto. Se as duas forem incompatíveis de verdade (uma
  desfaz a outra, ou exigem comportamentos opostos), pergunte ao usuário com `AskUserQuestion`,
  mostrando os dois trechos e o que cada um faz, e recomende uma saída.
- Num script, confira que o resultado continua válido (`python3 -m py_compile`, `bash -n`).
- Conflito `binario`: não dá para mesclar; `resultado/` tem o local. Pergunte qual fica e, se for
  o novo, copie `conflitos/<arquivo>.novo` para `resultado/<arquivo>`.

**Decidir.** Pergunte ao usuário (pode ser uma chamada só de `AskUserQuestion` para todos), dizendo
o que o repositório fez com o arquivo:

- `mudou-aqui-apagado-no-repositorio`: manter o do projeto (padrão) ou apagar (remova o arquivo de
  `resultado/`). Veja no diff se ele foi renomeado ou incorporado a outro: aí, leve o ajuste do
  projeto para o lugar novo, em `resultado/`.
- `apagado-aqui-mudou-no-repositorio`: continuar apagado (padrão) ou voltar com a versão nova
  (copie `conflitos/<arquivo>.novo` para `resultado/<arquivo>`).

## 4. Aplicar

```bash
python3 $A apply --work <work>
```

O script recusa se ainda houver marca de conflito ou se algum arquivo do projeto mudou depois do
`prepare` (nesse caso, rode o `prepare` de novo). Aplicado, ele grava os arquivos, apaga os
removidos, registra o commit novo em `.claude/esteira-versao.json` e apaga o diretório de trabalho.

Responda com:

- a versão nova e um resumo das novidades (pelos commits, em linguagem de quem usa);
- o que foi mesclado e como cada conflito foi resolvido, uma linha por arquivo;
- `reiniciar_loops: true`: os loops que já estão rodando continuam com o código antigo até
  reiniciar. Diga para fechar a aba 1 dos spaces e rodar `/esteira-up`. Não reinicie por conta
  própria;
- `skills_novas`: só aparecem depois de abrir o Claude de novo na pasta do projeto. As vagas
  abertas pegam as skills novas quando forem recicladas;
- se `.claude/skills/` está no git do projeto, sugira conferir com `git diff` e commitar. Não
  commite por conta própria.
