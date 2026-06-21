# Categorizador de PDFs por Ativo Financeiro

## Visão Geral

Categoriza automaticamente PDFs baixados via Telegram identificando ativos financeiros (ações B3 e FIIs) através de extração de texto + OCR, cria subpastas por ativo na pasta de trabalho e gera atalhos `.lnk` do Windows apontando para cada PDF.

## Regras de Negócio

- Pasta de trabalho configurada em `config.yaml` → campo `working_folder`
- Processa apenas PDFs na **raiz** da pasta de trabalho (sem recursão)
- Padrão de ativos: 4 letras maiúsculas + sufixo `3`, `4` ou `11` (ex: `PETR4`, `VALE3`, `MXRF11`)
- **Tickers encontrados exclusivamente em tabelas são ignorados** — se o ticker aparecer no corpo do texto (mesmo que também esteja em alguma tabela), ele é considerado normalmente; só é descartado quando a única ocorrência é dentro de uma célula de tabela (aplica-se a PDFs digitais; PDFs escaneados via OCR não têm separação estrutural)
- **Não apaga nenhum arquivo** — apenas cria pastas, atalhos e renomeia PDFs
- PDF processado → renomeado com `_categorizado` antes da extensão
- Atalho criado em `<working_folder>/<TICKER>/<nome_original> - <TICKER>.lnk`
- Se um PDF contém múltiplos ativos → uma pasta e um atalho por ativo

## Estrutura do Projeto

```
Resume_PDFs_Relatorios/
├── main.py                  # Ponto de entrada
├── config.yaml              # Configuração (pasta, OCR, regex, etc.)
├── requirements.txt
├── CLAUDE.md
├── src/
│   ├── config_loader.py     # Leitura de config.yaml e setup de logging
│   ├── pdf_processor.py     # Extração de texto (pdfplumber + OCR fallback)
│   ├── asset_detector.py    # Regex para identificar tickers
│   └── file_organizer.py    # Criação de pastas, atalhos e renomeação
└── tests/
    ├── test_asset_detector.py
    ├── test_file_organizer.py
    └── test_pdf_processor.py
```

## Pré-requisitos

### Python
```
pip install -r requirements.txt
```

### Tesseract OCR (obrigatório para PDFs escaneados)
Baixar e instalar: https://github.com/UB-Mannheim/tesseract/wiki
- Instalar com pacote de idioma Português (`por`)
- Ajustar `tesseract_cmd` em `config.yaml` se não estiver no PATH

### Poppler (obrigatório para conversão PDF→imagem)
Baixar: https://github.com/oschwartz10612/poppler-windows/releases
- Extrair e apontar `poppler_path` em `config.yaml` para a pasta `bin`

## Uso

```bash
# Execução normal
python main.py

# Execução com arquivo de configuração alternativo
python main.py --config outro_config.yaml

# Simulação (sem modificar arquivos)
python main.py --dry-run
```

## Configuração (`config.yaml`)

| Campo | Descrição | Padrão |
|-------|-----------|--------|
| `working_folder` | Pasta com os PDFs a processar | `C:\Users\dpf\Downloads\Telegram Desktop` |
| `reprocess_mode` | `skip` (pula _categorizado) ou `always` | `skip` |
| `asset_pattern` | Regex para tickers B3 | `\b[A-Z]{4}(?:11\|3\|4)\b` |
| `ocr.language` | Idiomas Tesseract | `por+eng` |
| `ocr.dpi` | DPI para conversão PDF→imagem | `300` |
| `ocr.min_text_length` | Chars mínimos antes de acionar OCR | `50` |
| `tesseract_cmd` | Caminho do executável Tesseract | `tesseract` |
| `poppler_path` | Pasta `bin` do Poppler (`null` = PATH) | `null` |

## Testes

```bash
pytest tests/ -v
```

## Arquitetura de Fluxo

```
PDF encontrado
    │
    ├─ já tem _categorizado?
    │       ├─ sim + reprocess_mode=skip → IGNORAR
    │       └─ não (ou reprocess_mode=always) ↓
    │
    ├─ extrair texto (pdfplumber — tabelas excluídas)
    │       └─ texto < min_text_length → OCR (pdf2image + Tesseract, sem exclusão de tabelas)
    │
    ├─ aplicar regex → set de tickers
    │       └─ vazio → registrar "sem ativos"
    │
    ├─ renomear PDF → original_categorizado.pdf
    │
    └─ para cada ticker:
            ├─ criar pasta <working_folder>/<TICKER>/ (se não existir)
            └─ criar atalho <nome_original> - <TICKER>.lnk
```

## Observações para Agentes

- `win32com.client` só funciona em Windows — testes que envolvem criação de atalhos devem usar mock
- O OCR requer Tesseract + Poppler instalados na máquina; sem eles, PDFs escaneados ficam sem texto
- Exclusão de tabelas usa `pdfplumber.page.find_tables()` + `page.filter(_build_table_filter(...))` — testável via `_build_table_filter` diretamente (ver `tests/test_pdf_processor.py`)
- Para PDFs escaneados (caminho OCR), a exclusão de tabelas **não é aplicada** — não há informação estrutural na imagem
- Falsos positivos conhecidos estão em `src/asset_detector.py::_FALSE_POSITIVES`
- `config.local.yaml` está no `.gitignore` — use-o para sobrescrever `config.yaml` sem commitar caminhos locais
