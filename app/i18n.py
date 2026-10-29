"""Lightweight UI internationalisation.

Translates the application's own interface text only — never user memory
content. English source strings are the keys; a missing translation falls back
to English. Language is chosen per request from the ``lang`` cookie.
"""
from __future__ import annotations

from typing import Callable

LANG_COOKIE = "lang"
DEFAULT_LANG = "en"
SUPPORTED_LANGS = ("en", "pt-BR")
LANG_LABELS = {"en": "EN", "pt-BR": "PT"}

# English source string -> Brazilian Portuguese. English is used verbatim when a
# key is absent here, so only translated strings need listing.
_PT_BR: dict[str, str] = {
    # Shell
    "Skip to content": "Pular para o conteúdo",
    "Second Brain home": "Início do Second Brain",
    "Toggle navigation": "Alternar navegação",
    "Primary navigation": "Navegação principal",
    "Memories": "Memórias",
    "Graph": "Grafo",
    "Tasks": "Tarefas",
    "Import": "Importar",
    "AI prompt": "Prompt de IA",
    "Language": "Idioma",
    "Second Brain / private memory atlas": "Second Brain / atlas de memória privado",
    "Source truth and AI advice stay visibly separate.":
        "A verdade das fontes e os conselhos da IA permanecem visivelmente separados.",
    # Dashboard
    "Memory atlas": "Atlas de memória",
    "Find the thread": "Encontre o fio",
    "you almost forgot.": "que você quase esqueceu.",
    "A searchable record of decisions, conversations, loose ends, and the context around them.":
        "Um registro pesquisável de decisões, conversas, pontas soltas e o contexto ao redor delas.",
    "Knowledge base summary": "Resumo da base de conhecimento",
    "Open tasks": "Tarefas abertas",
    "Questions": "Perguntas",
    "Search your context": "Pesquise seu contexto",
    "Decisions, people, systems, ideas…": "Decisões, pessoas, sistemas, ideias…",
    "Topic": "Tópico",
    "All topics": "Todos os tópicos",
    "From": "De",
    "To": "Até",
    "Explore": "Explorar",
    "Clear filters": "Limpar filtros",
    "Index": "Índice",
    "Topics": "Tópicos",
    "Your topic index will grow as memories arrive.":
        "Seu índice de tópicos crescerá conforme as memórias chegarem.",
    "Chronology": "Cronologia",
    "memory": "memória",
    "memories": "memórias",
    "+ Import JSON": "+ Importar JSON",
    "Date unknown": "Data desconhecida",
    "open": "abertas",
    "to learn": "a aprender",
    "Read": "Ler",
    "No matching thread.": "Nenhum fio correspondente.",
    "Your atlas starts empty.": "Seu atlas começa vazio.",
    "Try a broader search or clear the filters.":
        "Tente uma busca mais ampla ou limpe os filtros.",
    "Use the AI prompt with notes, email, or a transcript, then import the resulting JSON.":
        "Use o prompt de IA com notas, e-mails ou uma transcrição e importe o JSON resultante.",
    "Reset view": "Redefinir visão",
    "Get the prompt": "Obter o prompt",
    "Memory pages": "Páginas de memórias",
    "← Newer": "← Mais recentes",
    "Older →": "Mais antigas →",
    # Tasks
    "Task radar": "Radar de tarefas",
    "Loose ends,": "Pontas soltas,",
    "made visible.": "tornadas visíveis.",
    "Only commitments found in your source material appear here. AI recommendations stay separate.":
        "Apenas compromissos encontrados no seu material de origem aparecem aqui. As recomendações da IA ficam à parte.",
    "Overdue": "Atrasadas",
    "Past the stated deadline": "Após o prazo informado",
    "Next 14 days": "Próximos 14 dias",
    "Scheduled and approaching": "Agendadas e se aproximando",
    "Needs scheduling": "Precisam de agendamento",
    "No deadline was stated": "Nenhum prazo foi informado",
    "Later": "Mais tarde",
    "Beyond the next two weeks": "Além das próximas duas semanas",
    "Owner not stated": "Responsável não informado",
    "Unscheduled": "Sem agendamento",
    "Nothing here.": "Nada aqui.",
    "Mark concluded": "Marcar como concluída",
    "Mark concluded:": "Marcar como concluída:",
    "Task concluded": "Tarefa concluída",
    "The matching existing graph node was marked concluded too.":
        "O nó correspondente já existente no grafo também foi marcado como concluído.",
    "No graph node was created or changed because no unique existing match was found.":
        "Nenhum nó do grafo foi criado ou alterado porque não foi encontrada uma correspondência existente única.",
    "Archive": "Arquivo",
    "Concluded": "Concluídas",
    "Concluded on": "Concluída em",
    "Completed commitments remain visible as part of your record.":
        "Os compromissos concluídos permanecem visíveis como parte do seu registro.",
    "Completion time not recorded": "Horário de conclusão não registrado",
    "No concluded tasks yet.": "Ainda não há tarefas concluídas.",
    # Import
    "Import desk": "Mesa de importação",
    "Bring the day": "Traga o dia",
    "into focus.": "para o foco.",
    "Upload strict JSON produced with the unified Second Brain prompt. The complete file is validated before anything is stored.":
        "Envie o JSON estrito produzido com o prompt unificado do Second Brain. O arquivo completo é validado antes que qualquer coisa seja armazenada.",
    "Drop JSON files here": "Solte os arquivos JSON aqui",
    "or choose from your device": "ou escolha do seu dispositivo",
    "Up to": "Até",
    "MB per file": "MB por arquivo",
    "Validate & import": "Validar e importar",
    "Method": "Método",
    "Three steps": "Três passos",
    "Copy the prompt": "Copie o prompt",
    "Open it in ChatGPT, Claude, Copilot, or another capable model.":
        "Abra-o no ChatGPT, Claude, Copilot ou outro modelo capaz.",
    "Add your source": "Adicione sua fonte",
    "Paste notes, email, briefings, or transcript text after the divider.":
        "Cole notas, e-mails, briefings ou texto de transcrição após o divisor.",
    "Import the JSON": "Importe o JSON",
    "Save the model’s JSON response and upload it here.":
        "Salve a resposta JSON do modelo e envie-a aqui.",
    "Open the AI prompt →": "Abrir o prompt de IA →",
    "Accepted JSON formats": "Formatos JSON aceitos",
    "Recommended: unified atlas": "Recomendado: atlas unificado",
    "Populates memories, topics, tasks, search, and graph together.":
        "Preenche memórias, tópicos, tarefas, pesquisa e grafo em conjunto.",
    "Legacy memories": "Memórias legadas",
    "Populates memory views and is projected into the graph.":
        "Preenche as visualizações de memória e é projetado no grafo.",
    "Legacy graph only": "Somente grafo legado",
    "Populates only the graph; it cannot create grounded memories or tasks.":
        "Preenche somente o grafo; não pode criar memórias fundamentadas nem tarefas.",
    "Result": "Resultado",
    "Import report": "Relatório de importação",
    "memories.": "memórias.",
    "View imported memories": "Ver memórias importadas",
    "View graph": "Ver grafo",
    "Graph reconciliation preflight": "Pré-verificação de reconciliação do grafo",
    "new nodes": "novos nós",
    "exact-ID updates": "atualizações por ID exato",
    "identity merges": "mesclagens de identidade",
    "new edges": "novas arestas",
    "edge updates": "atualizações de arestas",
    "Likely duplicate identities": "Identidades provavelmente duplicadas",
    "Existing identities that will be updated": "Identidades existentes que serão atualizadas",
    "Manual correction required": "Correção manual necessária",
    "reuse projected identity": "reutilizar identidade projetada",
    "fold existing node into memory identity": "incorporar nó existente à identidade da memória",
    "reuse existing identity": "reutilizar identidade existente",
    "Choose the same JSON file again": "Escolha novamente o mesmo arquivo JSON",
    "Its checksum and reconciliation plan must match this preflight.":
        "O checksum e o plano de reconciliação devem corresponder a esta pré-verificação.",
    "I reviewed this plan. Apply the listed updates and identity merges atomically.":
        "Revisei este plano. Aplique atomicamente as atualizações e mesclagens de identidade listadas.",
    "Confirm & reconcile": "Confirmar e reconciliar",
    # Graph
    "Knowledge graph": "Grafo de conhecimento",
    "Trace how it all connects.": "Veja como tudo se conecta.",
    "Interactive force-directed knowledge graph. Drag to move nodes, scroll to zoom, click a node for details.":
        "Grafo de conhecimento interativo com força dirigida. Arraste para mover nós, role para dar zoom, clique em um nó para ver detalhes.",
    "Categories": "Categorias",
    "Graph controls": "Controles do grafo",
    "Search nodes": "Pesquisar nós",
    "AI links": "Links de IA",
    "Reset": "Redefinir",
    "Show all nodes": "Mostrar todos os nós",
    "Export all": "Exportar tudo",
    "Levels": "Níveis",
    "Export selection": "Exportar seleção",
    "Clear": "Limpar",
    "No graph yet.": "Nenhum grafo ainda.",
    "Get the unified AI prompt": "Obtenha o prompt unificado de IA",
    "to create memories and graph relationships together.":
        "para criar memórias e relações do grafo em conjunto.",
    "a schema 2.0 graph, or": "um grafo de esquema 2.0, ou",
    "get the AI prompt": "obtenha o prompt de IA",
    ". Existing memories appear here automatically.":
        ". As memórias existentes aparecem aqui automaticamente.",
    "Close details": "Fechar detalhes",
    "Could not load the graph.": "Não foi possível carregar o grafo.",
    # Prompt library
    "AI handoff": "Entrega para a IA",
    "Prompts that keep": "Prompts que mantêm",
    "memory honest.": "a memória honesta.",
    "Prepare a source with one of the review prompts, then create one unified JSON file for every Second Brain view.":
        "Prepare uma fonte com um dos prompts de revisão e crie um arquivo JSON unificado para todas as visualizações do Second Brain.",
    "Source preparation": "Preparação de fonte",
    "These produce a written report — not JSON. Feed that report into the schema generator.":
        "Estes produzem um relatório escrito — não JSON. Alimente esse relatório no gerador de esquema.",
    "Schema generator": "Gerador de esquema",
    "Creates memories, topics, tasks, search data, and graph relationships in one atomic import.":
        "Cria memórias, tópicos, tarefas, dados de pesquisa e relações do grafo em uma única importação atômica.",
    "Outputs a written report": "Produz um relatório escrito",
    "Outputs unified atlas JSON": "Produz JSON de atlas unificado",
    "Outputs graph JSON": "Produz JSON do grafo",
    "Outputs a presentation": "Produz uma apresentação",
    "Presentation": "Apresentação",
    "Export the graph as JSON, then turn it into a shareable presentation (single-page HTML, PPTX, or PDF).":
        "Exporte o grafo como JSON e transforme-o em uma apresentação compartilhável (HTML de página única, PPTX ou PDF).",
    "Presentation builder": "Gerador de apresentação",
    "Turn an exported graph into a single-page HTML, PPTX, or PDF presentation that explains the knowledge and how it connects.":
        "Transforme um grafo exportado em uma apresentação em HTML de página única, PPTX ou PDF que explica o conhecimento e como ele se conecta.",
    "Export JSON": "Exportar JSON",
    "Reveal prompt": "Revelar prompt",
    "Hide": "Ocultar",
    "Copy": "Copiar",
    "Copied": "Copiado",
    "Download .txt": "Baixar .txt",
    "JSON Schema": "Esquema JSON",
    "Loading…": "Carregando…",
    "Could not load this prompt.": "Não foi possível carregar este prompt.",
    "Email day review": "Revisão de e-mails do dia",
    "Review a day of email: important messages, tasks, who wrote, whether you replied, and what is still missing — with context.":
        "Revise um dia de e-mails: mensagens importantes, tarefas, quem escreveu, se você respondeu e o que ainda falta — com contexto.",
    "Meeting transcript review": "Revisão de transcrição de reunião",
    "Review a meeting recording transcript into decisions, actions, owners, and open questions.":
        "Revise a transcrição de uma gravação de reunião em decisões, ações, responsáveis e perguntas em aberto.",
    "Interactive daily report": "Relatório diário interativo",
    "Give it your day's notes and messages; it asks you focused questions, then writes a detailed daily report.":
        "Dê a ele as notas e mensagens do seu dia; ele faz perguntas objetivas e então escreve um relatório diário detalhado.",
    "Graph schema generator": "Gerador de esquema do grafo",
    "Unified atlas generator": "Gerador de atlas unificado",
    "Creates one grounded JSON file for memories, topics, tasks, search, and graph.":
        "Cria um arquivo JSON fundamentado para memórias, tópicos, tarefas, pesquisa e grafo.",
    # Memory detail
    "← Memory atlas": "← Atlas de memória",
    "Context": "Contexto",
    "People": "Pessoas",
    "Memory ID": "ID da memória",
    "What you know": "O que você sabe",
    "Source evidence": "Evidência da fonte",
    "Commitments": "Compromissos",
    "priority": "prioridade",
    "Mentioned, explained": "Mencionado, explicado",
    "Explanation:": "Explicação:",
    "What you still need": "O que você ainda precisa",
    "Recommendations": "Recomendações",
    "The following items are generated advice. They are not source facts or commitments.":
        "Os itens a seguir são conselhos gerados por IA. Não são fatos de origem nem compromissos.",
    # Topic detail
    "← All topics": "← Todos os tópicos",
    "Living dossier": "Dossiê vivo",
    "connected memories, assembled into what you know and what remains unresolved.":
        "memórias conectadas, reunidas no que você sabe e no que permanece sem resolução.",
    "Known": "Conhecido",
    "Grounded facts": "Fatos fundamentados",
    "No grounded facts are attached to this topic yet.":
        "Nenhum fato fundamentado está vinculado a este tópico ainda.",
    "Unknown": "Desconhecido",
    "What to learn": "O que aprender",
    "No explicit knowledge gaps for this topic.":
        "Nenhuma lacuna de conhecimento explícita para este tópico.",
    "From": "De",
    "AI advice": "Conselho da IA",
    "Possible next moves": "Possíveis próximos passos",
    "Archive": "Arquivo",
    "Connected memories": "Memórias conectadas",
    # 404
    "This thread": "Este fio",
    "isn’t in the atlas.": "não está no atlas.",
    "The memory or topic may have moved, or never existed.":
        "A memória ou o tópico pode ter mudado, ou nunca existiu.",
    "Return to memories": "Voltar às memórias",
    "Not found": "Não encontrado",
}

_CATALOG: dict[str, dict[str, str]] = {"pt-BR": _PT_BR}


def normalize_lang(value: str | None) -> str:
    if value in SUPPORTED_LANGS:
        return value
    return DEFAULT_LANG


def translator(lang: str) -> Callable[[str], str]:
    table = _CATALOG.get(lang, {})

    def t(text: str) -> str:
        return table.get(text, text)

    return t


def other_lang(lang: str) -> str:
    return "pt-BR" if lang == "en" else "en"
