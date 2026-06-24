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

### Python (ambiente virtual)
```bash
# Criar o venv (apenas na primeira vez)
python -m venv .venv

# Ativar o venv
.\.venv\Scripts\activate        # Windows PowerShell
# source .venv/bin/activate     # Linux/macOS

# Instalar dependências dentro do venv
pip install -r requirements.txt
```

> Sempre ative o venv antes de rodar o script ou os testes.

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

## Ambiente Python e Subprocessos — regra obrigatória

Este projeto usa `.venv` como ambiente virtual. Nunca invoque `python` ou `python.exe`
como string literal em subprocessos:

```python
# ERRADO — usa o Python do PATH do sistema (Anaconda), ignorando o .venv
subprocess.run(["python", "main.py"])
os.system("python main.py")
```

O Windows resolve `"python"` pelo PATH global, que aponta para o Anaconda instalado em
`C:\Users\dpf\anaconda3\python.exe`. Isso faz o subprocesso rodar fora do `.venv`,
sem acesso às dependências instaladas (pdfplumber, pytesseract, pdf2image, etc.),
causando `ModuleNotFoundError` ou comportamento inconsistente com o processo pai.

Esse problema foi identificado em produção: o processo pai (PID 19672) iniciava
corretamente pelo `.venv`, mas seus processos filhos e workers de multiprocessing
(PIDs 7072, 21496, 23616, 19532, 7640, 22864, 21412) rodavam com `anaconda3`.

**Correção obrigatória — use sempre `sys.executable`:**

```python
import sys, subprocess

# CORRETO — herda o mesmo interpretador do processo pai (.venv)
subprocess.run([sys.executable, "main.py"])
subprocess.Popen([sys.executable, "-m", "modulo"])

# Para multiprocessing, o spawn já herda sys.executable automaticamente
# desde que o bloco abaixo esteja presente em main.py:
if __name__ == "__main__":
    multiprocessing.freeze_support()
    ...
```

`sys.executable` retorna o caminho absoluto do interpretador atual
(ex: `G:\Meu Drive\Git\Projetos\Resume_PDFs_Relatorios\.venv\Scripts\python.exe`),
garantindo que todos os subprocessos e workers usem o mesmo `.venv`.

## Observações para Agentes

- `win32com.client` só funciona em Windows — testes que envolvem criação de atalhos devem usar mock
- O OCR requer Tesseract + Poppler instalados na máquina; sem eles, PDFs escaneados ficam sem texto
- Exclusão de tabelas usa `pdfplumber.page.find_tables()` + `page.filter(_build_table_filter(...))` — testável via `_build_table_filter` diretamente (ver `tests/test_pdf_processor.py`)
- Para PDFs escaneados (caminho OCR), a exclusão de tabelas **não é aplicada** — não há informação estrutural na imagem
- Falsos positivos conhecidos estão em `src/asset_detector.py::_FALSE_POSITIVES`
- `config.local.yaml` está no `.gitignore` — use-o para sobrescrever `config.yaml` sem commitar caminhos locais
