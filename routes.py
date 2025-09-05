from flask import render_template, request, jsonify, flash, redirect, url_for, session, send_file, send_from_directory
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import io
import os
import logging
from models import User, Level, Challenge, UserChallenge, Category, FAQ, Ticket, Team, db
from utils import process_ticket_command, suggest_solution, extract_faqs_from_pdf, create_admin_user
from services import find_faqs_by_keywords, find_faq_by_nlp, update_user_level
from config import Config, LEVELS
from flask_caching import Cache

logging.basicConfig(filename='admin_actions.log', level=logging.INFO)

def init_routes(app):
    cache = Cache(app)
    
    @app.context_processor
    def inject_user_gamification_data():
        if current_user.is_authenticated and current_user.level:
            return dict(user_level_insignia=current_user.level.insignia)
        return dict(user_level_insignia='?')

    @app.route('/uploads/insignias/<filename>')
    def uploaded_insignia(filename):
        return send_from_directory(app.config['INSIGNIA_FOLDER'], filename)

    @app.route('/')
    @login_required
    def index():
        return render_template('index.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            email = request.form['email']
            password = request.form['password']
            user = User.query.filter_by(email=email).first()
            if user and check_password_hash(user.password, password):
                user.last_login = datetime.utcnow()
                db.session.commit()
                login_user(user)
                next_page = request.args.get('next')
                flash('Login realizado com sucesso!', 'success')
                return redirect(next_page or url_for('index'))
            flash('Email ou senha inválidos.', 'error')
        return render_template('login.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            name = request.form['name']
            email = request.form['email']
            password = generate_password_hash(request.form['password'])
            phone = request.form.get('phone')
            initial_level = Level.query.filter_by(name='Iniciante').first()
            if not initial_level:
                flash('Erro: Nível "Iniciante" não encontrado.', 'error')
                return redirect(url_for('register'))
            if User.query.filter_by(email=email).first():
                flash('Email já registrado.', 'error')
            else:
                user = User(name=name, email=email, password=password, phone=phone, is_admin=False, level_id=initial_level.id)
                db.session.add(user)
                db.session.commit()
                flash('Registro concluído! Faça login.', 'success')
                return redirect(url_for('login'))
        return render_template('register.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        flash('Você saiu com sucesso.', 'success')
        return redirect(url_for('login'))

    @app.route('/chat-page')
    @login_required
    def chat_page():
        session.pop('faq_selection', None)
        return render_template('chat.html')

    @app.route('/chat', methods=['POST'])
    @login_required
    def chat():
        data = request.get_json()
        mensagem = data.get('mensagem', '').strip()
        resposta = {
            'text': "Desculpe, não entendi. Tente reformular a pergunta.",
            'html': False,
            'state': 'normal',
            'options': []
        }
        ticket_response = process_ticket_command(mensagem)
        if ticket_response:
            resposta['text'] = ticket_response
        else:
            solution_response = suggest_solution(mensagem)
            if solution_response:
                resposta['text'] = solution_response
            else:
                faq_matches = find_faq_by_nlp(mensagem)
                if faq_matches:
                    if len(faq_matches) == 1:
                        faq = faq_matches[0]
                        resposta['text'] = faq.formatted_answer
                        resposta['html'] = True
                    else:
                        faq_ids = [faq.id for faq in faq_matches]
                        session['faq_selection'] = faq_ids
                        resposta['state'] = 'faq_selection'
                        resposta['text'] = "Encontrei várias FAQs relacionadas. Clique na que você deseja:"
                        resposta['html'] = True
                        resposta['options'] = [{'id': faq.id, 'question': faq.question} for faq in faq_matches][:5]
                else:
                    resposta['text'] = "Nenhuma FAQ encontrada para a sua busca. Tente reformular a pergunta."
        return jsonify(resposta)

    @app.route('/profile', methods=['GET', 'POST'])
    @login_required
    def profile():
        if request.method == 'POST':
            current_user.phone = request.form.get('phone')
            db.session.commit()
            flash('Perfil atualizado com sucesso!', 'success')
            return redirect(url_for('profile'))
        return render_template('profile.html')

    @app.route('/faqs', methods=['GET'])
    @login_required
    @cache.cached(timeout=300)
    def faqs():
        categories = Category.query.all()
        faqs = FAQ.query.all()
        faq_to_edit = None
        if request.args.get('edit'):
            faq_id = request.args.get('edit')
            faq_to_edit = FAQ.query.get_or_404(faq_id)
        return render_template('faqs.html', faqs=faqs, categories=categories, faq_to_edit=faq_to_edit)

    @app.route('/faqs/edit/<int:faq_id>', methods=['GET', 'POST'])
    @login_required
    def edit_faq(faq_id):
        if not current_user.is_admin:
            flash('Acesso negado.', 'error')
            return redirect(url_for('faqs'))
        faq = FAQ.query.get_or_404(faq_id)
        if request.method == 'POST':
            faq.category_id = request.form['edit_category']
            faq.question = request.form['edit_question']
            faq.answer = request.form['edit_answer']
            faq.image_url = request.form.get('edit_image_url') or None
            faq.video_url = request.form.get('edit_video_url') or None
            file = request.files.get('edit_file')
            if file and file.filename:
                faq.file_name = file.filename
                faq.file_data = file.read()
            db.session.commit()
            cache.clear()
            flash('FAQ atualizada com sucesso!', 'success')
            return redirect(url_for('faqs'))
        return redirect(url_for('faqs', edit=faq_id))

    @app.route('/faqs/delete/<int:faq_id>', methods=['POST'])
    @login_required
    def delete_faq(faq_id):
        if not current_user.is_admin:
            flash('Acesso negado.', 'error')
            return redirect(url_for('faqs'))
        faq = FAQ.query.get_or_404(faq_id)
        logging.info(f'FAQ ID {faq_id} deleted by admin {current_user.email} at {datetime.utcnow()}')
        db.session.delete(faq)
        db.session.commit()
        cache.clear()
        flash('FAQ excluída com sucesso!', 'success')
        return redirect(url_for('faqs'))

    @app.route('/download/<int:faq_id>')
    @login_required
    def download(faq_id):
        faq = FAQ.query.get_or_404(faq_id)
        if faq.file_data:
            return send_file(io.BytesIO(faq.file_data), download_name=faq.file_name, as_attachment=True)
        flash('Nenhum arquivo encontrado.', 'error')
        return redirect(url_for('faqs'))

    @app.route('/admin/dashboard')
    @login_required
    def admin_dashboard():
        if not current_user.is_admin:
            flash('Acesso negado.', 'error')
            return redirect(url_for('index'))
        stats = {
            'total_users': User.query.count(),
            'total_faqs': FAQ.query.count(),
            'total_teams': Team.query.count(),
            'total_challenges_completed': UserChallenge.query.count(),
            'top_users': User.query.order_by(User.points.desc()).limit(5).all()
        }
        return render_template('admin_dashboard.html', stats=stats)

    @app.route('/admin/users')
    @login_required
    def admin_users():
        if not current_user.is_admin:
            flash('Acesso negado.', 'error')
            return redirect(url_for('index'))
        all_users = User.query.order_by(User.name).all()
        return render_template('admin_users.html', users=all_users)

    @app.route('/admin/toggle_admin/<int:user_id>', methods=['POST'])
    @login_required
    def toggle_admin(user_id):
        if not current_user.is_admin:
            flash('Acesso negado.', 'error')
            return redirect(url_for('index'))
        user_to_modify = User.query.get_or_404(user_id)
        if user_to_modify.id == current_user.id:
            flash('Você não pode remover a sua própria permissão de administrador.', 'error')
            return redirect(url_for('admin_users'))
        user_to_modify.is_admin = not user_to_modify.is_admin
        db.session.commit()
        status = "administrador" if user_to_modify.is_admin else "utilizador normal"
        flash(f'O utilizador {user_to_modify.name} é agora um {status}.', 'success')
        return redirect(url_for('admin_users'))

    @app.route('/admin/faq', methods=['GET', 'POST'])
    @login_required
    def admin_faq():
        if not current_user.is_admin:
            flash('Acesso negado.', 'error')
            return redirect(url_for('index'))
        categories = Category.query.all()
        if request.method == 'POST':
            if 'add_question' in request.form:
                category_id = request.form['category']
                question = request.form['question']
                answer = request.form['answer']
                image_url = request.form.get('image_url')
                video_url = request.form.get('video_url')
                file = request.files.get('file')
                file_name = file.filename if file else None
                file_data = file.read() if file else None
                if category_id and question and answer:
                    faq = FAQ(category_id=category_id, question=question, answer=answer, image_url=image_url, video_url=video_url, file_name=file_name, file_data=file_data)
                    db.session.add(faq)
                    db.session.commit()
                    cache.clear()
                    flash('FAQ adicionada com sucesso!', 'success')
                else:
                    flash('Preencha todos os campos obrigatórios.', 'error')
            elif 'import_faqs' in request.form:
                file = request.files['faq_file']
                if file and file.filename.endswith(('.json', '.csv', '.pdf')):
                    filename = secure_filename(file.filename)
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(file_path)
                    try:
                        if file.filename.endswith('.json'):
                            with open(file_path, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                                if not isinstance(data, list):
                                    flash('Arquivo JSON deve conter uma lista de FAQs.', 'error')
                                    os.remove(file_path)
                                    return redirect(url_for('admin_faq'))
                                for item in data:
                                    category_name = item.get('category')
                                    question = item.get('question')
                                    answer = item.get('answer', '')
                                    image_url = item.get('image_url')
                                    video_url = item.get('video_url')
                                    file_name = item.get('file_name')
                                    file_data = item.get('file_data', None)
                                    if not category_name or not question:
                                        flash('Cada FAQ no JSON deve ter "category" e "question".', 'error')
                                        continue
                                    category = Category.query.filter_by(name=category_name).first()
                                    if not category:
                                        category = Category(name=category_name)
                                        db.session.add(category)
                                        db.session.commit()
                                    faq = FAQ(category_id=category.id, question=question, answer=answer, image_url=image_url, video_url=video_url, file_name=file_name, file_data=file_data)
                                    db.session.add(faq)
                        elif file.filename.endswith('.csv'):
                            category_id = request.form['category_import']
                            with open(file_path, 'r', encoding='utf-8') as f:
                                reader = csv.DictReader(f)
                                for row in reader:
                                    faq = FAQ(
                                        category_id=category_id,
                                        question=row.get('question'),
                                        answer=row.get('answer', ''),
                                        image_url=row.get('image_url'),
                                        video_url=row.get('video_url'),
                                        file_name=row.get('file_name'),
                                        file_data=row.get('file_data')
                                    )
                                    db.session.add(faq)
                        elif file.filename.endswith('.pdf'):
                            category_id = request.form['category_import']
                            faqs_extracted, error = extract_faqs_from_pdf(file_path)
                            if error:
                                flash(error, 'error')
                            for faq in faqs_extracted:
                                new_faq = FAQ(category_id=category_id, question=faq['question'], answer=faq['answer'], image_url=None, video_url=None, file_name=None, file_data=None)
                                db.session.add(new_faq)
                        db.session.commit()
                        flash('FAQs importadas com sucesso!', 'success')
                    except Exception as e:
                        flash(f'Erro ao importar FAQs: {str(e)}', 'error')
                    finally:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                else:
                    flash('Formato de arquivo inválido. Use JSON, CSV ou PDF.', 'error')
        return render_template('admin_faq.html', categories=categories)

    @app.route('/admin/export/faqs')
    @login_required
    def export_faqs():
        if not current_user.is_admin:
            flash('Acesso negado.', 'error')
            return redirect(url_for('index'))
        faqs = FAQ.query.all()
        faqs_list = [
            {
                'category': faq.category.name,
                'question': faq.question,
                'answer': faq.answer,
                'image_url': faq.image_url,
                'video_url': faq.video_url
            } for faq in faqs
        ]
        response = jsonify(faqs_list)
        response.headers['Content-Disposition'] = 'attachment; filename=faqs_backup.json'
        return response

    @app.route('/admin/challenges', methods=['GET', 'POST'])
    @login_required
    def admin_challenges():
        if not current_user.is_admin:
            flash('Acesso negado.', 'error')
            return redirect(url_for('index'))
        if request.method == 'POST':
            title = request.form.get('title')
            description = request.form.get('description')
            level_required = request.form.get('level_required')
            points_reward = request.form.get('points_reward', type=int)
            expected_answer = request.form.get('expected_answer')
            unlocks_faq_id = request.form.get('unlocks_faq_id')
            if unlocks_faq_id and unlocks_faq_id.isdigit():
                unlocks_faq_id = int(unlocks_faq_id)
            else:
                unlocks_faq_id = None
            new_challenge = Challenge(
                title=title,
                description=description,
                level_required=level_required,
                points_reward=points_reward,
                expected_answer=expected_answer,
                unlocks_faq_id=unlocks_faq_id
            )
            db.session.add(new_challenge)
            db.session.commit()
            flash('Novo desafio adicionado com sucesso!', 'success')
            return redirect(url_for('admin_challenges'))
        all_challenges = Challenge.query.order_by(Challenge.id).all()
        all_faqs = FAQ.query.order_by(FAQ.question).all()
        return render_template('admin_challenges.html', challenges=all_challenges, faqs=all_faqs, levels=LEVELS)

    @app.route('/challenges')
    @login_required
    def list_challenges():
        completed_challenges_ids = [uc.challenge_id for uc in current_user.completed_challenges]
        user_level_min_points = LEVELS.get(current_user.level.name, {}).get('min_points', 0)
        available_challenges_query = Challenge.query.filter(Challenge.id.notin_(completed_challenges_ids))
        unlocked_challenges = []
        locked_challenges = []
        for challenge in available_challenges_query.all():
            challenge_level_min_points = LEVELS.get(challenge.level_required, {}).get('min_points', float('inf'))
            if user_level_min_points >= challenge_level_min_points:
                unlocked_challenges.append(challenge)
            else:
                locked_challenges.append(challenge)
        return render_template('challenges.html', unlocked_challenges=unlocked_challenges, locked_challenges=locked_challenges)

    @app.route('/challenges/submit/<int:challenge_id>', methods=['POST'])
    @login_required
    def submit_challenge(challenge_id):
        challenge = Challenge.query.get_or_404(challenge_id)
        user_level_min_points = LEVELS.get(current_user.level.name, {}).get('min_points', 0)
        challenge_level_min_points = LEVELS.get(challenge.level_required, {}).get('min_points', float('inf'))
        if user_level_min_points < challenge_level_min_points:
            flash(f'Você precisa estar no nível "{challenge.level_required}" para submeter este desafio.', 'error')
            return redirect(url_for('list_challenges'))
        submitted_answer = request.form.get('answer', '').strip()
        if not submitted_answer:
            flash('Por favor, forneça uma resposta.', 'error')
            return redirect(url_for('list_challenges'))
        if submitted_answer == challenge.expected_answer:
            existing_completion = UserChallenge.query.filter_by(user_id=current_user.id, challenge_id=challenge_id).first()
            if not existing_completion:
                current_user.points += challenge.points_reward
                message = update_user_level(current_user)
                completion = UserChallenge(user_id=current_user.id, challenge_id=challenge_id)
                db.session.add(completion)
                db.session.commit()
                flash(f'Parabéns! Você completou o desafio "{challenge.title}" e ganhou {challenge.points_reward} pontos!', 'success')
                if message:
                    flash(message, 'success')
            else:
                flash('Você já completou este desafio.', 'info')
        else:
            flash('Resposta incorreta. Tente novamente!', 'error')
        return redirect(url_for('list_challenges'))

    @app.route('/teams', methods=['GET', 'POST'])
    @login_required
    def teams_list():
        if request.method == 'POST':
            if current_user.team_id:
                flash('Você já pertence a um time. Saia do seu time atual para criar um novo.', 'error')
                return redirect(url_for('teams_list'))
            team_name = request.form.get('team_name')
            if Team.query.filter_by(name=team_name).first():
                flash('Já existe um time com este nome.', 'error')
            else:
                new_team = Team(name=team_name, owner_id=current_user.id)
                db.session.add(new_team)
                current_user.team = new_team
                db.session.commit()
                flash(f'Time "{team_name}" criado com sucesso!', 'success')
                return redirect(url_for('teams_list'))
        all_teams = Team.query.all()
        return render_template('teams.html', teams=all_teams)

    @app.route('/teams/join/<int:team_id>', methods=['POST'])
    @login_required
    def join_team(team_id):
        if current_user.team_id:
            flash('Você já pertence a um time.', 'error')
            return redirect(url_for('teams_list'))
        team_to_join = Team.query.get_or_404(team_id)
        current_user.team = team_to_join
        db.session.commit()
        flash(f'Você entrou no time "{team_to_join.name}"!', 'success')
        return redirect(url_for('teams_list'))

    @app.route('/teams/leave', methods=['POST'])
    @login_required
    def leave_team():
        if not current_user.team_id:
            flash('Você não pertence a nenhum time.', 'error')
            return redirect(url_for('teams_list'))
        team = current_user.team
        if team.owner_id == current_user.id:
            flash('Você é o dono do time e não pode sair.', 'warning')
            return redirect(url_for('teams_list'))
        current_user.team_id = None
        db.session.commit()
        flash(f'Você saiu do time "{team.name}".', 'success')
        return redirect(url_for('teams_list'))

    @app.route('/team/manage')
    @login_required
    def manage_team():
        if not current_user.team:
            flash('Você não pertence a um time.', 'error')
            return redirect(url_for('teams_list'))
        team = current_user.team
        if team.owner_id != current_user.id:
            flash('Apenas o dono do time pode gerir os membros.', 'error')
            return redirect(url_for('teams_list'))
        return render_template('manage_team.html', team=team)

    @app.route('/team/kick/<int:user_id>', methods=['POST'])
    @login_required
    def kick_from_team(user_id):
        if not current_user.team or current_user.team.owner_id != current_user.id:
            flash('Acesso negado.', 'error')
            return redirect(url_for('teams_list'))
        user_to_kick = User.query.get_or_404(user_id)
        if user_to_kick.team_id != current_user.team_id:
            flash('Este utilizador não pertence ao seu time.', 'error')
            return redirect(url_for('manage_team'))
        if user_to_kick.id == current_user.id:
            flash('Você não pode expulsar a si mesmo.', 'error')
            return redirect(url_for('manage_team'))
        user_to_kick.team_id = None
        db.session.commit()
        flash(f'O utilizador {user_to_kick.name} foi removido do time.', 'success')
        return redirect(url_for('manage_team'))

    @app.route('/admin/levels', methods=['GET', 'POST'])
    @login_required
    def admin_levels():
        if not current_user.is_admin:
            flash('Acesso negado.', 'error')
            return redirect(url_for('index'))
        if request.method == 'POST':
            name = request.form.get('name')
            min_points = request.form.get('min_points', type=int)
            insignia_file = request.files.get('insignia_image')
            filename = 'default.png'
            if insignia_file and insignia_file.filename:
                filename = secure_filename(insignia_file.filename)
                insignia_file.save(os.path.join(app.config['INSIGNIA_FOLDER'], filename))
            new_level = Level(name=name, min_points=min_points, insignia=filename)
            db.session.add(new_level)
            db.session.commit()
            flash('Novo nível criado com sucesso!', 'success')
            return redirect(url_for('admin_levels'))
        levels = Level.query.order_by(Level.min_points.asc()).all()
        return render_template('admin_levels.html', levels=levels)

    @app.route('/admin/teams')
    @login_required
    def admin_teams():
        if not current_user.is_admin:
            flash('Acesso negado.', 'error')
            return redirect(url_for('index'))
        all_teams = Team.query.all()
        return render_template('admin_teams.html', teams=all_teams)

    @app.route('/admin/teams/delete/<int:team_id>', methods=['POST'])
    @login_required
    def admin_delete_team(team_id):
        if not current_user.is_admin:
            flash('Acesso negado.', 'error')
            return redirect(url_for('index'))
        team_to_delete = Team.query.get_or_404(team_id)
        for member in team_to_delete.members:
            member.team_id = None
        db.session.delete(team_to_delete)
        db.session.commit()
        flash(f'O time "{team_to_delete.name}" foi dissolvido.', 'success')
        return redirect(url_for('admin_teams'))

    @app.route('/ranking')
    @login_required
    @cache.cached(timeout=300)
    def ranking():
        ranked_users = User.query.order_by(User.points.desc()).all()
        ranked_teams = sorted(Team.query.all(), key=lambda t: t.total_points, reverse=True)
        return render_template('ranking.html', ranked_users=ranked_users, ranked_teams=ranked_teams, LEVELS=LEVELS)