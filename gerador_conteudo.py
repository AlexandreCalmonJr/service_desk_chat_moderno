import json

def gerar_faqs():
    """Gera uma lista de FAQs focada em Python e TI geral."""
    faqs = [
        # FAQs de Python
        {
            "category": "Automation",
            "question": "O que é uma variável em Python?",
            "answer": "Uma variável é como uma 'caixa' na memória do computador onde você pode guardar um valor (um número, um texto, etc.) e dar um nome a ela. Por exemplo, `idade = 25` cria uma variável chamada 'idade' e guarda o número 25 nela.",
            "image_url": "https://placehold.co/400x200/f59e0b/ffffff?text=idade+%3D+25",
            "video_url": "https://www.youtube.com/watch?v=ZHQLmrOjKgA"
        },
        {
            "category": "Automation",
            "question": "Qual a diferença entre uma lista e uma tupla em Python?",
            "answer": "Ambas guardam coleções de itens, mas a principal diferença é que as listas são 'mutáveis' (pode adicionar ou remover itens depois de criadas) e usam parênteses retos `[]`. Tuplas são 'imutáveis' (não pode alterá-las) e usam parênteses `()`. Tuplas são geralmente mais rápidas.",
            "image_url": None,
            "video_url": "https://www.youtube.com/watch?v=0zYuLLIzPIQ"
        },
        {
            "category": "Automation",
            "question": "Como se escreve um comentário em código Python?",
            "answer": "Para escrever um comentário de uma linha em Python, use o símbolo de cardinal (#). Tudo o que vier depois do # naquela linha será ignorado pelo interpretador. Ex: `# Isto é um comentário.`",
            "image_url": None,
            "video_url": "http://youtube.com/watch?v=NttqIkFycb8"
        },
        # FAQs Gerais
        {
            "category": "Software",
            "question": "Como instalo o Microsoft Office na minha máquina?",
            "answer": "Para instalar o Office, acesse o portal da empresa, vá para a seção de downloads de software e siga o guia de instalação para Windows ou macOS. Você precisará de permissões de administrador.",
            "image_url": "https://placehold.co/400x250/0078D4/ffffff?text=Guia+de+Instalação",
            "video_url": None
        },
        {
            "category": "Rede",
            "question": "Como me conectar à VPN da empresa?",
            "answer": "Abra o cliente VPN (ex: Cisco AnyConnect), digite o endereço do servidor fornecido pelo TI, e use seu utilizador e senha de rede para se conectar.",
            "image_url": None,
            "video_url": "https://www.youtube.com/watch?v=examplevideo"
        }
    ]
    with open('faqs.json', 'w', encoding='utf-8') as f:
        json.dump(faqs, f, indent=4, ensure_ascii=False)
    print("Ficheiro 'faqs.json' gerado com sucesso!")

def gerar_desafios():
    """Gera uma lista de desafios focada em Fundamentos de Python."""
    desafios = [
        # Nível Iniciante
        {
            "title": "Olá, Mundo!",
            "description": "Escreva uma função em Python chamada 'ola_mundo' que use a função print() para exibir a mensagem 'Olá, Mundo!'.",
            "level_required": "Iniciante", "points_reward": 10, "challenge_type": "code",
            "expected_answer": "def ola_mundo():\n    print('Olá, Mundo!')",
            "expected_output": "A saída no console deve ser exatamente: Olá, Mundo!"
        },
        {
            "title": "Verificador de Idade (if/else)",
            "description": "Escreva uma função 'pode_votar' que recebe uma idade e retorna 'Pode votar' se a idade for 16 ou mais, e 'Não pode votar' caso contrário.",
            "level_required": "Iniciante", "points_reward": 15, "challenge_type": "code",
            "expected_answer": "def pode_votar(idade):\n    if idade >= 16:\n        return 'Pode votar'\n    else:\n        return 'Não pode votar'",
            "expected_output": "Para pode_votar(18) a saída deve ser 'Pode votar'."
        },
        {
            "title": "Cérebro do Computador",
            "description": "Qual componente de hardware é conhecido como o 'cérebro' do computador?",
            "level_required": "Iniciante", "points_reward": 10, "challenge_type": "text",
            "expected_answer": "CPU",
            "expected_output": None
        },
        # Nível Básico
        {
            "title": "Filtrar Números Pares (Listas)",
            "description": "Crie uma função 'filtra_pares' que recebe uma lista de números e retorna uma nova lista contendo apenas os números pares.",
            "level_required": "Básico", "points_reward": 25, "challenge_type": "code",
            "expected_answer": "def filtra_pares(numeros):\n    return [n for n in numeros if n % 2 == 0]",
            "expected_output": "Para [1, 2, 3, 4, 5, 6] a saída deve ser [2, 4, 6]."
        },
        {
            "title": "Contagem com Loop For",
            "description": "Crie uma função 'contagem' que usa um loop 'for' para imprimir os números de 1 a 5, um por linha.",
            "level_required": "Básico", "points_reward": 20, "challenge_type": "code",
            "expected_answer": "def contagem():\n    for i in range(1, 6):\n        print(i)",
            "expected_output": "A saída deve ser os números de 1 a 5 impressos em linhas separadas."
        },
        # Nível Intermediário
        {
            "title": "Acessar E-mail no Dicionário",
            "description": "Dado um dicionário de utilizador, crie uma função 'get_email' que retorna o valor associado à chave 'email'.",
            "level_required": "Intermediário", "points_reward": 30, "challenge_type": "code",
            "expected_answer": "def get_email(utilizador):\n    return utilizador.get('email')",
            "expected_output": "Para {'nome': 'Ana', 'email': 'ana@exemplo.com'} a saída deve ser 'ana@exemplo.com'."
        },
        {
            "title": "Verificador de Palíndromo (Strings)",
            "description": "Escreva uma função 'eh_palindromo' que verifica se uma palavra é um palíndromo (lê-se da mesma forma de trás para a frente), retornando True ou False.",
            "level_required": "Intermediário", "points_reward": 35, "challenge_type": "code",
            "expected_answer": "def eh_palindromo(palavra):\n    return palavra.lower() == palavra.lower()[::-1]",
            "expected_output": "Para 'arara' a saída deve ser True. Para 'python' deve ser False."
        }
    ]
    with open('desafios.json', 'w', encoding='utf-8') as f:
        json.dump(desafios, f, indent=4, ensure_ascii=False)
    print("Ficheiro 'desafios.json' gerado com sucesso!")

def gerar_trilha():
    """Gera uma trilha de aprendizagem completa sobre Python."""
    trilha = {
        "name": "Jornada do Conhecimento Python",
        "description": "Domine os pilares da programação em Python, desde a sintaxe básica até a manipulação de estruturas de dados.",
        "reward_points": 200,
        "is_active": True,
        "challenges": [
            {"title": "Olá, Mundo!", "step": 1},
            {"title": "Verificador de Idade (if/else)", "step": 2},
            {"title": "Contagem com Loop For", "step": 3},
            {"title": "Filtrar Números Pares (Listas)", "step": 4},
            {"title": "Acessar E-mail no Dicionário", "step": 5},
            {"title": "Verificador de Palíndromo (Strings)", "step": 6}
        ]
    }
    with open('trilha_python.json', 'w', encoding='utf-8') as f:
        json.dump(trilha, f, indent=4, ensure_ascii=False)
    print("Ficheiro 'trilha_python.json' gerado com sucesso!")

def gerar_boss():
    """Gera uma Boss Fight temática sobre depuração de código Python."""
    boss = {
        "name": "O Bug Tirano",
        "description": "Um bug misterioso corrompeu os sistemas centrais! A vossa equipa de elite deve mergulhar no código, identificar e esmagar os erros em cada etapa para restaurar a ordem.",
        "reward_points": 600,
        "image_url": "https://placehold.co/600x400/ef4444/ffffff?text=BUG+DETECTED",
        "is_active": True,
        "stages": [
            {
                "name": "Depuração: Erros de Sintaxe", "order": 1,
                "steps": [
                    {"description": "O código 'if x > 5 print(\"Maior\")' tem um erro de sintaxe. Qual é o caracter que falta?", "expected_answer": ":"},
                    {"description": "Uma função foi definida como 'def minha funcao():'. Qual é o erro no nome da função?", "expected_answer": "espaço"}
                ]
            },
            {
                "name": "Depuração: Erros de Lógica", "order": 2,
                "steps": [
                    {"description": "O código 'if a = 10:' tenta comparar 'a' com 10, mas usa o operador errado. Qual é o operador de comparação correto?", "expected_answer": "=="},
                    {"description": "Um loop 'for i in range(5):' irá executar quantas vezes?", "expected_answer": "5"}
                ]
            },
            {
                "name": "Depuração: O Desafio Final", "order": 3,
                "steps": [
                    {"description": "A função `len()` serve para obter o quê de uma lista ou string?", "expected_answer": "comprimento"},
                    {"description": "Para adicionar um item ao final de uma lista chamada `minha_lista`, qual método usamos? (ex: minha_lista.metodo(item))", "expected_answer": "append"}
                ]
            }
        ]
    }
    with open('boss_fight.json', 'w', encoding='utf-8') as f:
        json.dump(boss, f, indent=4, ensure_ascii=False)
    print("Ficheiro 'boss_fight.json' gerado com sucesso!")

if __name__ == "__main__":
    print("A gerar ficheiros de conteúdo com tema de Fundamentos de Python...")
    gerar_faqs()
    gerar_desafios()
    gerar_trilha()
    gerar_boss()
    print("\nTodos os ficheiros foram gerados com sucesso na pasta do projeto.")

