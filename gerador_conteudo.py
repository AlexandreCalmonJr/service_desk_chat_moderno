import json

def gerar_faqs():
    """Retorna uma lista de FAQs focada em Python e TI geral."""
    return [
        {
            "category": "Automation",
            "question": "O que é uma variável em Python?",
            "answer": "Uma variável é como uma 'caixa' na memória do computador onde você pode guardar um valor (um número, um texto, etc.) e dar um nome a ela. Por exemplo, `idade = 25` cria uma variável chamada 'idade' e guarda o número 25 nela.",
            "image_url": "https://placehold.co/400x200/f59e0b/ffffff?text=idade+%3D+25",
            "video_url": "https://www.youtube.com/watch?v=ZHQLmrOjKgA"
        },
        # Adicione mais FAQs se desejar
    ]

def gerar_desafios():
    """Retorna uma lista de desafios focada em Fundamentos de Python."""
    return [
        {
            "title": "Olá, Mundo!",
            "description": "Escreva uma função em Python chamada 'ola_mundo' que use a função print() para exibir a mensagem 'Olá, Mundo!'.",
            "level_required": "Iniciante", "points_reward": 10, "challenge_type": "code",
            "expected_answer": "def ola_mundo():\n    print('Olá, Mundo!')",
            "expected_output": "A saída no console deve ser exatamente: Olá, Mundo!"
        },
        {
            "title": "Cérebro do Computador",
            "description": "Qual componente de hardware é conhecido como o 'cérebro' do computador?",
            "level_required": "Iniciante", "points_reward": 10, "challenge_type": "text",
            "expected_answer": "CPU",
            "expected_output": None
        },
    ]

def gerar_trilhas():
    """Retorna uma lista de trilhas de aprendizagem."""
    return [
        {
            "name": "Jornada do Conhecimento Python",
            "description": "Domine os pilares da programação em Python, desde a sintaxe básica até a manipulação de estruturas de dados.",
            "reward_points": 200,
            "is_active": True,
            "challenges": [
                {"title": "Olá, Mundo!", "step": 1},
                {"title": "Cérebro do Computador", "step": 2},
            ]
        }
    ]

def gerar_boss_fights():
    """Retorna uma lista de Boss Fights."""
    return [
        {
            "name": "O Bug Tirano",
            "description": "Um bug misterioso corrompeu os sistemas centrais! A vossa equipa de elite deve mergulhar no código, identificar e esmagar os erros em cada etapa para restaurar a ordem.",
            "reward_points": 600,
            "image_url": "https://placehold.co/600x400/ef4444/ffffff?text=BUG+DETECTED",
            "is_active": True,
            "stages": [
                {"name": "Depuração: Erros de Sintaxe", "order": 1, "steps": [{"description": "O código 'if x > 5 print(\"Maior\")' tem um erro de sintaxe. Qual é o caracter que falta?", "expected_answer": ":"}]},
                {"name": "Depuração: Erros de Lógica", "order": 2, "steps": [{"description": "O código 'if a = 10:' tenta comparar 'a' com 10. Qual é o operador errado?", "expected_answer": "=="}]},
            ]
        }
    ]

def gerar_caca_tesouros():
    """Retorna uma lista de eventos de Caça ao Tesouro."""
    return [
        {
            "name": "A Caça ao Código Perdido",
            "description": "Uma série de enigmas testará seu conhecimento da plataforma e de Python.",
            "reward_points": 300,
            "is_active": True,
            "steps": [
                {
                    "step_number": 1,
                    "clue_text": "Para começar, encontre a FAQ que explica a 'diferença entre uma lista e uma tupla'.",
                    "target_type": "FAQ",
                    "target_identifier": "diferença entre uma lista e uma tupla",
                    "hidden_clue": "PISTA ENCONTRADA: O 'cérebro' do computador detém o próximo segredo."
                },
                {
                    "step_number": 2,
                    "clue_text": "Agora, encontre e resolva o desafio sobre o 'Cérebro do Computador'.",
                    "target_type": "CHALLENGE",
                    "target_identifier": "Cérebro do Computador",
                    "hidden_clue": "PISTA FINAL: O terrível Bug Tirano guarda o tesouro."
                }
            ]
        }
    ]

def gerar_eventos_globais():
    """Retorna uma lista de Eventos Globais (World Bosses)."""
    return [
        {
            "name": "Invasão do Vírus Corruptor",
            "description": "Um vírus global ameaça todo o sistema! Todos os agentes devem se unir. Cada desafio completado causa dano direto ao vírus.",
            "total_hp": 50000,
            "start_date": "2025-10-01T09:00:00", # Formato ISO simplificado
            "end_date": "2025-10-03T21:00:00",
            "is_active": True,
            "reward_points_on_win": 150
        }
    ]

if __name__ == "__main__":
    print("A gerar ficheiro de conteúdo unificado...")

    conteudo_completo = {
        "faqs": gerar_faqs(),
        "desafios": gerar_desafios(),
        "trilhas": gerar_trilhas(),
        "boss_fights": gerar_boss_fights(),
        "caca_tesouros": gerar_caca_tesouros(),
        "eventos_globais": gerar_eventos_globais()
    }

    with open('conteudo_completo.json', 'w', encoding='utf-8') as f:
        json.dump(conteudo_completo, f, indent=4, ensure_ascii=False)
    
    print("\nFicheiro 'conteudo_completo.json' foi gerado com sucesso.")

