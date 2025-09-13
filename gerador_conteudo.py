import json

def gerar_desafios_12_casas():
    """
    Cria os 12 desafios de Python, cada um representando uma Casa do Zodíaco.
    A dificuldade progride de conceitos básicos a mais avançados.
    """
    return [
        # Casa 1: Áries
        {
            "title": "Casa de Áries: A Muralha de Cristal",
            "description": "Mu de Áries ensina o básico da defesa: imprimir mensagens. Crie uma função que use print() para exibir 'Pelo poder do Zodíaco!'.",
            "level_required": "Iniciante", "points_reward": 10, "challenge_type": "code",
            "expected_answer": "def elevar_cosmo():\n    print('Pelo poder do Zodíaco!')",
            "expected_output": "A saída deve ser 'Pelo poder do Zodíaco!'."
        },
        # Casa 2: Touro
        {
            "title": "Casa de Touro: O Grande Chifre",
            "description": "Aldebaran testa sua força com operações. Crie uma função que recebe dois números, `a` e `b`, e retorna a soma e a multiplicação deles como uma string formatada: 'Soma: X, Multiplicação: Y'.",
            "level_required": "Iniciante", "points_reward": 15, "challenge_type": "code",
            "expected_answer": "def grande_chifre(a, b):\n    return f\"Soma: {a + b}, Multiplicação: {a * b}\"",
            "expected_output": "Para (a=10, b=5), a saída deve ser 'Soma: 15, Multiplicação: 50'."
        },
        # Casa 3: Gêmeos
        {
            "title": "Casa de Gêmeos: O Labirinto da Ilusão",
            "description": "Saga cria uma ilusão com condicionais. Crie uma função 'caminho_correto' que recebe um número. Se for par, retorne 'Caminho da Luz'. Se for ímpar, retorne 'Caminho das Sombras'.",
            "level_required": "Iniciante", "points_reward": 20, "challenge_type": "code",
            "expected_answer": "def caminho_correto(numero):\n    if numero % 2 == 0:\n        return 'Caminho da Luz'\n    else:\n        return 'Caminho das Sombras'",
            "expected_output": "Para numero=10, a saída é 'Caminho da Luz'."
        },
        # Casa 4: Câncer
        {
            "title": "Casa de Câncer: As Ondas do Inferno",
            "description": "Máscara da Morte envia almas com loops. Crie uma função 'ondas_do_inferno' que usa um loop 'for' para imprimir os números de 1 a 6, representando as 6 reencarnações.",
            "level_required": "Básico", "points_reward": 25, "challenge_type": "code",
            "expected_answer": "def ondas_do_inferno():\n    for i in range(1, 7):\n        print(i)",
            "expected_output": "Os números de 1 a 6, um em cada linha."
        },
        # Casa 5: Leão
        {
            "title": "Casa de Leão: O Relâmpago de Plasma",
            "description": "Aiolia ataca com a velocidade das funções. Crie uma função 'capsula_do_poder' que recebe uma lista de números e retorna a soma de todos eles.",
            "level_required": "Básico", "points_reward": 30, "challenge_type": "code",
            "expected_answer": "def capsula_do_poder(numeros):\n    return sum(numeros)",
            "expected_output": "Para [1, 2, 3, 4], o retorno deve ser 10."
        },
        # Casa 6: Virgem
        {
            "title": "Casa de Virgem: O Tesouro do Céu",
            "description": "Shaka remove seus sentidos com listas. Crie uma função 'tesouro_do_ceu' que recebe uma lista e remove o último item dela, retornando a lista modificada.",
            "level_required": "Básico", "points_reward": 35, "challenge_type": "code",
            "expected_answer": "def tesouro_do_ceu(sentidos):\n    sentidos.pop()\n    return sentidos",
            "expected_output": "Para ['visão', 'audição', 'tato'], o retorno é ['visão', 'audição']."
        },
        # Casa 7: Libra
        {
            "title": "Casa de Libra: As Armas de Libra",
            "description": "O Mestre Ancião oferece as armas (dicionários). Crie uma função 'arma_de_libra' que recebe um dicionário de armas e retorna o valor da chave 'Escudo'.",
            "level_required": "Intermediário", "points_reward": 40, "challenge_type": "code",
            "expected_answer": "def arma_de_libra(armas):\n    return armas.get('Escudo')",
            "expected_output": "Para {'Espada': 1, 'Escudo': 2}, o retorno é 2."
        },
        # Casa 8: Escorpião
        {
            "title": "Casa de Escorpião: A Agulha Escarlate",
            "description": "Milo ataca 15 vezes com um loop 'while'. Crie uma função 'agulha_escarlate' que imprime 'Antares!' 15 vezes.",
            "level_required": "Intermediário", "points_reward": 45, "challenge_type": "code",
            "expected_answer": "def agulha_escarlate():\n    count = 0\n    while count < 15:\n        print('Antares!')\n        count += 1",
            "expected_output": "A palavra 'Antares!' impressa 15 vezes."
        },
        # Casa 9: Sagitário
        {
            "title": "Casa de Sagitário: A Flecha da Justiça",
            "description": "Aiolos dispara uma flecha precisa com list comprehension. Crie uma função 'flecha_da_justica' que recebe uma lista de números e retorna uma nova lista com cada número ao quadrado.",
            "level_required": "Intermediário", "points_reward": 50, "challenge_type": "code",
            "expected_answer": "def flecha_da_justica(numeros):\n    return [n**2 for n in numeros]",
            "expected_output": "Para [1, 2, 3, 4], o retorno é [1, 4, 9, 16]."
        },
        # Casa 10: Capricórnio
        {
            "title": "Casa de Capricórnio: A Excalibur",
            "description": "Shura corta tudo com a manipulação de strings. Crie uma função 'excalibur' que recebe uma frase e retorna apenas os 10 primeiros caracteres.",
            "level_required": "Avançado", "points_reward": 55, "challenge_type": "code",
            "expected_answer": "def excalibur(frase):\n    return frase[:10]",
            "expected_output": "Para 'Pelo futuro de Atena!', o retorno é 'Pelo futur'."
        },
        # Casa 11: Aquário
        {
            "title": "Casa de Aquário: O Esquife de Gelo",
            "description": "Camus congela o oponente com módulos. Crie uma função 'esquife_de_gelo' que importa o módulo 'random' e retorna um número inteiro aleatório entre 0 e 273.",
            "level_required": "Avançado", "points_reward": 60, "challenge_type": "code",
            "expected_answer": "import random\n\ndef esquife_de_gelo():\n    return random.randint(0, 273)",
            "expected_output": "Um número aleatório entre 0 e 273."
        },
        # Casa 12: Peixes
        {
            "title": "Casa de Peixes: As Rosas Diabólicas",
            "description": "Afrodite ataca com a beleza das classes. Crie uma classe 'Cavaleiro' com um método `__init__` que define `nome` e `constelacao`, e um método `atacar` que retorna 'Meteoro de Pégaso!'.",
            "level_required": "Avançado", "points_reward": 70, "challenge_type": "code",
            "expected_answer": "class Cavaleiro:\n    def __init__(self, nome, constelacao):\n        self.nome = nome\n        self.constelacao = constelacao\n\n    def atacar(self):\n        return 'Meteoro de Pégaso!'",
            "expected_output": "O código deve definir a classe 'Cavaleiro' corretamente."
        }
    ]

def gerar_faqs_cdz():
    """Gera FAQs de suporte para os conceitos de Python abordados nos desafios."""
    return [
        {"category": "Automation", "question": "O que é a função print() em Python?", "answer": "A função `print()` é usada para exibir informações (texto, números, variáveis) na tela ou console. É a ferramenta fundamental para ver o resultado do seu código."},
        {"category": "Automation", "question": "Como funcionam os operadores matemáticos (+, -, *, /) em Python?", "answer": "Eles funcionam como na matemática tradicional. `+` para somar, `-` para subtrair, `*` para multiplicar e `/` para dividir. Use parênteses `()` para controlar a ordem das operações."},
        {"category": "Automation", "question": "O que é uma estrutura condicional if/else?", "answer": "Permite que seu código tome decisões. O bloco `if` executa se uma condição for verdadeira, e o bloco `else` executa se for falsa."},
        {"category": "Automation", "question": "Para que serve o loop 'for'?", "answer": "O loop `for` é usado para repetir um bloco de código um número específico de vezes, geralmente para percorrer os itens de uma lista ou usar a função `range()`."},
        {"category": "Automation", "question": "O que são funções em Python?", "answer": "Funções são blocos de código reutilizáveis que realizam uma tarefa específica. Elas ajudam a organizar o código, evitar repetição e torná-lo mais legível."},
        {"category": "Automation", "question": "Como manipular listas em Python (adicionar, remover itens)?", "answer": "Você pode usar métodos como `.append(item)` para adicionar ao final, `.insert(indice, item)` para adicionar numa posição, e `.pop(indice)` ou `.remove(item)` para remover itens."},
        {"category": "Automation", "question": "Qual a utilidade de um dicionário?", "answer": "Dicionários guardam dados em pares de `chave: valor`. São extremamente úteis para representar objetos do mundo real, como um utilizador com chaves 'nome' e 'email'."},
        {"category": "Automation", "question": "Quando devo usar um loop 'while'?", "answer": "Use um loop `while` quando quiser que um bloco de código se repita enquanto uma condição for verdadeira, mas você não sabe exatamente quantas vezes isso vai acontecer."},
        {"category": "Automation", "question": "O que é List Comprehension?", "answer": "É uma forma curta e elegante de criar listas. A sintaxe `[expressao for item in lista]` permite criar uma nova lista baseada numa existente de forma muito concisa."},
        {"category": "Automation", "question": "Como acedo a partes de um texto (string slicing)?", "answer": "Você pode usar a notação de fatias (slicing). `texto[:5]` pega os primeiros 5 caracteres, `texto[-5:]` pega os últimos 5, e `texto[2:6]` pega do terceiro ao sexto caractere."},
        {"category": "Automation", "question": "O que são módulos em Python?", "answer": "Módulos são ficheiros Python com código que você pode importar para usar no seu próprio programa. A biblioteca padrão do Python vem com muitos módulos úteis como `math` para matemática e `random` para aleatoriedade."},
        {"category": "Automation", "question": "O que é uma classe em Programação Orientada a Objetos?", "answer": "Uma classe é um 'molde' para criar objetos. Ela define as propriedades (atributos) e os comportamentos (métodos) que os seus objetos terão. Por exemplo, uma classe 'Carro' pode ter atributos como 'cor' e 'marca'."},
    ]

def gerar_trilha_santuario():
    """Cria a Trilha de Aprendizagem principal da Saga das 12 Casas."""
    return [
        {
            "name": "A Saga das 12 Casas de Python",
            "description": "Atravesse as 12 Casas do Zodíaco, derrote os Cavaleiros de Ouro e domine os fundamentos de Python para salvar Atena!",
            "reward_points": 500,
            "is_active": True,
            "challenges": [
                {"title": "Casa de Áries: A Muralha de Cristal", "step": 1},
                {"title": "Casa de Touro: O Grande Chifre", "step": 2},
                {"title": "Casa de Gêmeos: O Labirinto da Ilusão", "step": 3},
                {"title": "Casa de Câncer: As Ondas do Inferno", "step": 4},
                {"title": "Casa de Leão: O Relâmpago de Plasma", "step": 5},
                {"title": "Casa de Virgem: O Tesouro do Céu", "step": 6},
                {"title": "Casa de Libra: As Armas de Libra", "step": 7},
                {"title": "Casa de Escorpião: A Agulha Escarlate", "step": 8},
                {"title": "Casa de Sagitário: A Flecha da Justiça", "step": 9},
                {"title": "Casa de Capricórnio: A Excalibur", "step": 10},
                {"title": "Casa de Aquário: O Esquife de Gelo", "step": 11},
                {"title": "Casa de Peixes: As Rosas Diabólicas", "step": 12}
            ]
        }
    ]

def gerar_boss_final():
    """Cria a Boss Fight final contra o Grande Mestre."""
    return [
        {
            "name": "O Grande Mestre Arles",
            "description": "Você chegou ao salão do Grande Mestre! Ele testará todo o seu conhecimento de Python num desafio final. Use tudo o que aprendeu para derrotá-lo!",
            "reward_points": 1000,
            "image_url": "https://placehold.co/600x400/4a044e/ffffff?text=O+GRANDE+MESTRE",
            "is_active": True,
            "stages": [
                {
                    "name": "Outra Dimensão", "order": 1,
                    "steps": [
                        {"description": "O Mestre cria uma lista de planetas: `['Mercúrio', 'Vênus', 'Terra']`. Qual comando adiciona 'Marte' ao final da lista?", "expected_answer": "planetas.append('Marte')"},
                        {"description": "Para verificar se 'Saturno' está na lista, qual seria a expressão condicional completa em Python?", "expected_answer": "if 'Saturno' in planetas:"}
                    ]
                },
                {
                    "name": "Explosão Galáctica", "order": 2,
                    "steps": [
                        {"description": "O Mestre ataca com um dicionário: `ataque = {'nome': 'Explosão Galáctica', 'poder': 9000}`. Como você acede ao valor do poder?", "expected_answer": "ataque['poder']"},
                        {"description": "Para unir todos os conceitos, escreva uma função `ataque_final` que recebe uma lista de números e retorna a soma apenas dos números maiores que 100.", "expected_answer": "def ataque_final(numeros):\n    return sum([n for n in numeros if n > 100])"}
                    ]
                }
            ]
        }
    ]

if __name__ == "__main__":
    print("Gerando conteúdo temático: A Saga das 12 Casas de Python...")

    conteudo_completo = {
        "faqs": gerar_faqs_cdz(),
        "desafios": gerar_desafios_12_casas(),
        "trilhas": gerar_trilha_santuario(),
        "boss_fights": gerar_boss_final(),
        "caca_tesouros": [], # Pode adicionar caças ao tesouro temáticas aqui no futuro
        "eventos_globais": [] # Pode adicionar eventos globais temáticos aqui no futuro
    }

    with open('conteudo_cdz_python.json', 'w', encoding='utf-8') as f:
        json.dump(conteudo_completo, f, indent=4, ensure_ascii=False)
    
    print("\nFicheiro 'conteudo_cdz_python.json' foi gerado com sucesso!")
    print("Use o botão 'Importar Conteúdo' no seu painel de administração para carregar esta nova campanha.")
