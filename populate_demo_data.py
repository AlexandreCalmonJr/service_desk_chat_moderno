"""
Script para popular o banco de dados com conteúdo de demonstração
"""
from app import app, db, User, Team, FAQ, Category, Challenge, LearningPath, PathChallenge
from app import BossFight, BossFightStage, BossFightStep, Achievement, DailyChallenge, Level
from werkzeug.security import generate_password_hash
from datetime import date
import random

def populate_database():
    with app.app_context():
        print("🚀 Iniciando população do banco de dados...\n")
        
        # Verificar se já existe conteúdo
        if FAQ.query.count() > 0 or Challenge.query.count() > 0:
            print("⚠️  Banco de dados já contém dados. Limpando dados antigos...")
            # Limpar dados existentes (exceto usuários e níveis)
            FAQ.query.delete()
            Challenge.query.delete()
            PathChallenge.query.delete()
            LearningPath.query.delete()
            BossFightStep.query.delete()
            BossFightStage.query.delete()
            BossFight.query.delete()
            Achievement.query.delete()
            DailyChallenge.query.delete()
            Team.query.filter(Team.id > 0).delete()  # Manter estrutura
            db.session.commit()
        
        # 1. CRIAR CATEGORIAS
        print("📁 Criando categorias...")
        categories = {}
        cat_names = ['Python Básico', 'Python Avançado', 'Web Development', 'Data Science', 'Algoritmos']
        for cat_name in cat_names:
            cat = Category.query.filter_by(name=cat_name).first()
            if not cat:
                cat = Category(name=cat_name)
                db.session.add(cat)
                db.session.commit()
            categories[cat_name] = cat
        print(f"   ✓ {len(categories)} categorias criadas\n")
        
        # 2. CRIAR FAQs
        print("📚 Criando FAQs...")
        faqs_data = [
            {
                'category': 'Python Básico',
                'question': 'O que é Python?',
                'answer': 'Python é uma linguagem de programação de alto nível, interpretada e de propósito geral. É conhecida por sua sintaxe clara e legível, tornando-a ideal para iniciantes.\n\nCaracterísticas principais:\n• Sintaxe simples e intuitiva\n• Multiplataforma\n• Grande comunidade e bibliotecas\n• Versátil (web, data science, automação, etc.)'
            },
            {
                'category': 'Python Básico',
                'question': 'Como declarar variáveis em Python?',
                'answer': 'Em Python, você não precisa declarar o tipo da variável explicitamente. Basta atribuir um valor:\n\nExemplos:\nnome = "João"  # String\nidade = 25     # Integer\naltura = 1.75  # Float\nativo = True   # Boolean\n\nPython é dinamicamente tipado, então a variável pode mudar de tipo durante a execução.'
            },
            {
                'category': 'Python Básico',
                'question': 'Quais são os tipos de dados básicos em Python?',
                'answer': 'Python possui vários tipos de dados nativos:\n\n1. Numéricos:\n   • int (inteiros): 42, -10\n   • float (decimais): 3.14, -0.5\n   • complex (complexos): 2+3j\n\n2. Texto:\n   • str (strings): "Olá", \'Python\'\n\n3. Booleanos:\n   • bool: True, False\n\n4. Sequências:\n   • list: [1, 2, 3]\n   • tuple: (1, 2, 3)\n   • range: range(10)\n\n5. Mapeamento:\n   • dict: {"nome": "João", "idade": 25}\n\n6. Conjuntos:\n   • set: {1, 2, 3}\n   • frozenset: frozenset([1, 2, 3])'
            },
            {
                'category': 'Python Avançado',
                'question': 'O que são decoradores em Python?',
                'answer': 'Decoradores são funções que modificam o comportamento de outras funções ou métodos. São uma forma elegante de adicionar funcionalidade.\n\nExemplo:\n\ndef meu_decorador(func):\n    def wrapper():\n        print("Antes da função")\n        func()\n        print("Depois da função")\n    return wrapper\n\n@meu_decorador\ndef dizer_ola():\n    print("Olá!")\n\nUsos comuns:\n• Logging\n• Autenticação\n• Medição de performance\n• Cache'
            },
            {
                'category': 'Web Development',
                'question': 'O que é Flask?',
                'answer': 'Flask é um microframework web para Python. É leve, flexível e fácil de aprender.\n\nCaracterísticas:\n• Minimalista e modular\n• Roteamento simples\n• Templates Jinja2\n• Servidor de desenvolvimento integrado\n• Extensível com plugins\n\nExemplo básico:\n\nfrom flask import Flask\napp = Flask(__name__)\n\n@app.route(\'/\')\ndef home():\n    return "Olá, Flask!"\n\nif __name__ == \'__main__\':\n    app.run()'
            },
            {
                'category': 'Data Science',
                'question': 'O que é NumPy?',
                'answer': 'NumPy é a biblioteca fundamental para computação científica em Python. Fornece arrays multidimensionais e funções matemáticas de alto desempenho.\n\nRecursos principais:\n• Arrays N-dimensionais eficientes\n• Operações vetorizadas\n• Funções matemáticas\n• Álgebra linear\n• Geração de números aleatórios\n\nExemplo:\nimport numpy as np\n\narr = np.array([1, 2, 3, 4, 5])\nprint(arr.mean())  # Média\nprint(arr.std())   # Desvio padrão'
            },
            {
                'category': 'Algoritmos',
                'question': 'O que é complexidade de tempo Big O?',
                'answer': 'Big O é uma notação que descreve o desempenho de um algoritmo conforme o tamanho da entrada cresce.\n\nComplexidades comuns:\n• O(1) - Constante: acesso a array por índice\n• O(log n) - Logarítmica: busca binária\n• O(n) - Linear: percorrer array\n• O(n log n) - Linearítmica: merge sort\n• O(n²) - Quadrática: bubble sort\n• O(2ⁿ) - Exponencial: fibonacci recursivo\n\nQuanto menor o Big O, mais eficiente o algoritmo!'
            }
        ]
        
        for faq_data in faqs_data:
            faq = FAQ(
                category_id=categories[faq_data['category']].id,
                question=faq_data['question'],
                answer=faq_data['answer']
            )
            db.session.add(faq)
        db.session.commit()
        print(f"   ✓ {len(faqs_data)} FAQs criadas\n")
        
        # 3. CRIAR DESAFIOS INDIVIDUAIS
        print("🎯 Criando desafios individuais...")
        challenges_data = [
            {
                'title': 'Hello World em Python',
                'description': 'Escreva um programa que imprime "Hello, World!" na tela.',
                'expected_answer': 'print("Hello, World!")',
                'points': 10,
                'level': 'Iniciante',
                'hint': 'Use a função print() para exibir texto na tela.'
            },
            {
                'title': 'Soma de Dois Números',
                'description': 'Crie uma função que recebe dois números e retorna a soma deles.',
                'expected_answer': 'def soma(a, b): return a + b',
                'points': 15,
                'level': 'Iniciante',
                'hint': 'Use def para criar uma função e return para retornar o resultado.'
            },
            {
                'title': 'Verificar Número Par',
                'description': 'Escreva uma função que verifica se um número é par.',
                'expected_answer': 'def eh_par(n): return n % 2 == 0',
                'points': 15,
                'level': 'Iniciante',
                'hint': 'Use o operador módulo (%) para verificar o resto da divisão por 2.'
            },
            {
                'title': 'Inverter String',
                'description': 'Crie uma função que inverte uma string.',
                'expected_answer': 'def inverter(s): return s[::-1]',
                'points': 20,
                'level': 'Básico',
                'hint': 'Use slicing com [::-1] para inverter a string.'
            },
            {
                'title': 'Contar Vogais',
                'description': 'Escreva uma função que conta quantas vogais existem em uma string.',
                'expected_answer': 'def contar_vogais(s): return sum(1 for c in s.lower() if c in "aeiou")',
                'points': 25,
                'level': 'Básico',
                'hint': 'Use um loop e verifique se cada caractere está em "aeiou".'
            },
            {
                'title': 'Fibonacci',
                'description': 'Implemente uma função que retorna o n-ésimo número da sequência de Fibonacci.',
                'expected_answer': 'def fibonacci(n): return n if n <= 1 else fibonacci(n-1) + fibonacci(n-2)',
                'points': 30,
                'level': 'Intermediário',
                'hint': 'Use recursão: fib(n) = fib(n-1) + fib(n-2), com casos base fib(0)=0 e fib(1)=1.'
            },
            {
                'title': 'Ordenação Bubble Sort',
                'description': 'Implemente o algoritmo Bubble Sort para ordenar uma lista.',
                'expected_answer': 'def bubble_sort(arr): n = len(arr); [arr.sort() for _ in range(n)]',
                'points': 35,
                'level': 'Intermediário',
                'hint': 'Compare elementos adjacentes e troque se estiverem fora de ordem.'
            },
            {
                'title': 'Palíndromo',
                'description': 'Crie uma função que verifica se uma palavra é um palíndromo.',
                'expected_answer': 'def eh_palindromo(s): return s == s[::-1]',
                'points': 20,
                'level': 'Básico',
                'hint': 'Compare a string com ela mesma invertida.'
            }
        ]
        
        for ch_data in challenges_data:
            challenge = Challenge(
                title=ch_data['title'],
                description=ch_data['description'],
                expected_answer=ch_data['expected_answer'],
                points_reward=ch_data['points'],
                level_required=ch_data['level'],
                hint=ch_data['hint'],
                hint_cost=5,
                is_team_challenge=False,
                challenge_type='text'
            )
            db.session.add(challenge)
        db.session.commit()
        print(f"   ✓ {len(challenges_data)} desafios individuais criados\n")
        
        # 4. CRIAR DESAFIOS DE TIME
        print("👥 Criando desafios de time...")
        team_challenges_data = [
            {
                'title': 'Projeto Web com Flask',
                'description': 'Criem juntos uma aplicação web simples com Flask que tenha pelo menos 3 rotas.',
                'expected_answer': 'aplicacao_flask',
                'points': 100,
                'level': 'Intermediário'
            },
            {
                'title': 'Análise de Dados em Equipe',
                'description': 'Usem Pandas para analisar um dataset e apresentar 5 insights interessantes.',
                'expected_answer': 'analise_dados',
                'points': 120,
                'level': 'Avançado'
            }
        ]
        
        for tch_data in team_challenges_data:
            challenge = Challenge(
                title=tch_data['title'],
                description=tch_data['description'],
                expected_answer=tch_data['expected_answer'],
                points_reward=tch_data['points'],
                level_required=tch_data['level'],
                hint='Trabalhem juntos e dividam as tarefas!',
                hint_cost=10,
                is_team_challenge=True,
                challenge_type='text'
            )
            db.session.add(challenge)
        db.session.commit()
        print(f"   ✓ {len(team_challenges_data)} desafios de time criados\n")
        
        # 5. CRIAR TRILHAS DE APRENDIZAGEM
        print("🛤️  Criando trilhas de aprendizagem...")
        path = LearningPath(
            name='Fundamentos de Python',
            description='Aprenda os conceitos básicos de Python do zero!',
            reward_points=50,
            is_active=True
        )
        db.session.add(path)
        db.session.commit()
        
        # Adicionar desafios à trilha
        basic_challenges = Challenge.query.filter(
            Challenge.level_required == 'Iniciante'
        ).limit(3).all()
        
        for idx, challenge in enumerate(basic_challenges, 1):
            path_challenge = PathChallenge(
                path_id=path.id,
                challenge_id=challenge.id,
                step=idx
            )
            db.session.add(path_challenge)
        db.session.commit()
        print(f"   ✓ 1 trilha criada com {len(basic_challenges)} desafios\n")
        
        # 6. CRIAR BOSS FIGHT
        print("⚔️  Criando Boss Fight...")
        boss = BossFight(
            name='O Dragão do Python',
            description='Um desafio épico que testará todo o conhecimento da sua equipe em Python!',
            reward_points=300,
            is_active=True
        )
        db.session.add(boss)
        db.session.commit()
        
        # Criar estágios do Boss Fight
        stage1 = BossFightStage(
            boss_fight_id=boss.id,
            name='Fundamentos',
            order=1
        )
        db.session.add(stage1)
        db.session.commit()
        
        # Criar tarefas do estágio 1
        steps_stage1 = [
            {'description': 'Criar uma função que calcula fatorial', 'answer': 'fatorial'},
            {'description': 'Implementar busca binária', 'answer': 'busca_binaria'},
            {'description': 'Criar um gerador de números primos', 'answer': 'primos'}
        ]
        
        for step_data in steps_stage1:
            step = BossFightStep(
                stage_id=stage1.id,
                description=step_data['description'],
                expected_answer=step_data['answer']
            )
            db.session.add(step)
        
        stage2 = BossFightStage(
            boss_fight_id=boss.id,
            name='Estruturas de Dados',
            order=2
        )
        db.session.add(stage2)
        db.session.commit()
        
        steps_stage2 = [
            {'description': 'Implementar uma pilha (Stack)', 'answer': 'stack'},
            {'description': 'Implementar uma fila (Queue)', 'answer': 'queue'},
            {'description': 'Criar uma árvore binária', 'answer': 'binary_tree'}
        ]
        
        for step_data in steps_stage2:
            step = BossFightStep(
                stage_id=stage2.id,
                description=step_data['description'],
                expected_answer=step_data['answer']
            )
            db.session.add(step)
        
        db.session.commit()
        print(f"   ✓ Boss Fight criado com 2 estágios e 6 tarefas\n")
        
        # 7. CRIAR CONQUISTAS
        print("🏆 Criando conquistas...")
        achievements_data = [
            {
                'name': 'Primeiro Passo',
                'description': 'Complete seu primeiro desafio',
                'icon': '🎯',
                'trigger_type': 'challenges_completed',
                'trigger_value': 1
            },
            {
                'name': 'Aprendiz Dedicado',
                'description': 'Complete 10 desafios',
                'icon': '📚',
                'trigger_type': 'challenges_completed',
                'trigger_value': 10
            },
            {
                'name': 'Mestre Python',
                'description': 'Alcance 500 pontos',
                'icon': '🐍',
                'trigger_type': 'points_earned',
                'trigger_value': 500
            },
            {
                'name': 'Jogador de Equipe',
                'description': 'Entre em um time',
                'icon': '👥',
                'trigger_type': 'first_team_join',
                'trigger_value': 1
            },
            {
                'name': 'Explorador de Trilhas',
                'description': 'Complete uma trilha de aprendizagem',
                'icon': '🗺️',
                'trigger_type': 'paths_completed',
                'trigger_value': 1
            }
        ]
        
        for ach_data in achievements_data:
            achievement = Achievement(
                name=ach_data['name'],
                description=ach_data['description'],
                icon=ach_data['icon'],
                trigger_type=ach_data['trigger_type'],
                trigger_value=ach_data['trigger_value']
            )
            db.session.add(achievement)
        db.session.commit()
        print(f"   ✓ {len(achievements_data)} conquistas criadas\n")
        
        # 8. CRIAR TIMES DE EXEMPLO
        print("🎮 Criando times de exemplo...")
        users = User.query.filter(User.is_admin == False).all()
        if len(users) >= 1:
            # Criar time 1
            team1 = Team(
                name='Pythonistas',
                owner_id=users[0].id
            )
            db.session.add(team1)
            db.session.commit()
            
            users[0].team_id = team1.id
            
            # Criar time 2 se houver mais usuários
            if len(users) >= 2:
                team2 = Team(
                    name='Code Warriors',
                    owner_id=users[1].id if len(users) > 1 else users[0].id
                )
                db.session.add(team2)
                db.session.commit()
            
            db.session.commit()
            print(f"   ✓ Times criados\n")
        
        # 9. DEFINIR DESAFIO DO DIA
        print("📅 Definindo desafio do dia...")
        today = date.today()
        daily = DailyChallenge.query.filter_by(day=today).first()
        if not daily:
            random_challenge = random.choice(Challenge.query.filter_by(is_team_challenge=False).all())
            daily = DailyChallenge(
                day=today,
                challenge_id=random_challenge.id,
                bonus_points=20
            )
            db.session.add(daily)
            db.session.commit()
        print(f"   ✓ Desafio do dia definido\n")
        
        print("=" * 60)
        print("✅ BANCO DE DADOS POPULADO COM SUCESSO!")
        print("=" * 60)
        print("\n📊 Resumo do conteúdo criado:")
        print(f"   • {FAQ.query.count()} FAQs")
        print(f"   • {Challenge.query.filter_by(is_team_challenge=False).count()} Desafios Individuais")
        print(f"   • {Challenge.query.filter_by(is_team_challenge=True).count()} Desafios de Time")
        print(f"   • {LearningPath.query.count()} Trilhas de Aprendizagem")
        print(f"   • {BossFight.query.count()} Boss Fights")
        print(f"   • {Achievement.query.count()} Conquistas")
        print(f"   • {Team.query.count()} Times")
        print(f"\n🌐 Acesse: http://127.0.0.1:5000")

if __name__ == "__main__":
    populate_database()
