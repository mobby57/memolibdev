\# MemoLibDev



> Un assistant de code local, gratuit, qui refuse de modifier vos fichiers sans votre accord.



\## Le probleme



Les assistants de code modernes (Cursor, Copilot, Kiro) coutent 20 $/mois chacun.

Ils modifient vos fichiers sans toujours montrer ce qu'ils font.

Ils ne peuvent pas revenir en arriere si quelque chose casse.



\## Notre reponse



MemoLibDev est un assistant de code qui :



\- Comprend une mission en francais

\- Genere un diff via un LLM local (Ollama)

\- Affiche le diff AVANT d'appliquer

\- Attend votre approbation explicite

\- Rollback automatique si la verification echoue

\- Trace tout (SHA-256, diff, statut)



\*\*Cout : 0 $/mois. Local. Tracable. Honnete.\*\*



\## Installation rapide



1\. Telechargez MemoLibDev.exe sur la page des Releases

2\. Double-cliquez dessus

3\. C'est tout.



\## Prerequis



\- Windows 10/11

\- Ollama : https://ollama.com/download

\- Un modele : ollama pull qwen2.5-coder:7b



\## Utilisation



\### Interface graphique



python memolibdev\_gui\_modern.py



\### Ligne de commande



$env:MEMOLIBDEV\_TARGET = "C:\\chemin\\vers\\projet"

python memolibdev\_cli.py --mission "votre mission" --mode PROPOSE --model qwen2.5-coder:7b



\## Les 4 modes



| Mode | Ecriture | Description |

|---|---|---|

| READ\_ONLY | Non | Analyse pure |

| PROPOSE | Non | Propose un diff |

| SANDBOX | Copie | Applique sur une copie |

| SUPERVISED\_APPLY | Oui | Applique apres approbation |



\## Securite



\- Aucune modification sans approbation explicite

\- Rollback automatique si echec

\- Trace chainee (SHA-256)

\- Fail-closed : refuse d'agir en cas de doute



\## Philosophie



Il ne dit pas PASS s'il n'a pas de preuve.

Il ne dit pas APPLIED s'il n'a pas verifie.

Il ne modifie rien sans votre accord explicite.



\## Licence



MIT

