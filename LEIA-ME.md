# Radar da Câmara de Jardinópolis

Site que mostra, só com dados oficiais da Câmara (SAPL), presença, propostas e votos de cada vereador.

## Como funciona
Todo dia às 03h17 (Brasília) o robô (`.github/workflows/atualizar.yml`):
1. baixa os dados na API da Câmara (`coletar.py`);
2. confere se vieram completos e coerentes (`validar.py`);
3. **se passou**: guarda os dados em `dados/`, gera o site (`gerar.py`) e publica;
4. **se não passou**: não publica. O site continua com a última versão boa.

Em qualquer caso, a branch `status` recebe o relatório da execução (`resultado.md`, `verificacao.txt`, `coleta.txt`, `explorar.txt`).

## Ligar a publicação (uma vez)
Settings > Pages > Source: **GitHub Actions**.

## Rodar na hora
Actions > "Atualizar e publicar o site" > Run workflow. A opção `forcar` aceita uma mudança grande nos números; ela nunca pula os testes de coerência.

## Ajustes
- `config.json`: cidade, endereço do SAPL, data inicial, lugares extras e limites (`validacao`).
- `regras.py`: regra única de classificação das propostas.
- `testes/teste_validar.py`: prova que dados ruins são bloqueados.

## Fotos dos vereadores (opcional)
Coloque os arquivos na pasta `fotos/`, com o número do vereador no SAPL como nome (ex.: `fotos/5.jpg`, `.png` ou `.webp`). O número aparece no endereço da ficha, em `.../parlamentar/5`. Onde houver foto, o crachá usa a foto; onde não houver, usa as iniciais. Use só fotos que você tem direito de publicar.
