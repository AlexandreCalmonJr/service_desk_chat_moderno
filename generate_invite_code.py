"""
Script para gerar código de convite
"""
from app import app, db, InvitationCode
import uuid

def generate_invite():
    with app.app_context():
        # Criar código de convite
        invitation_code = str(uuid.uuid4())
        invitation = InvitationCode(code=invitation_code, used=False)
        db.session.add(invitation)
        db.session.commit()
        
        print(f"\n{'='*60}")
        print(f"CÓDIGO DE CONVITE GERADO:")
        print(f"{invitation_code}")
        print(f"{'='*60}\n")
        print("Use este código para criar uma nova conta em:")
        print("http://127.0.0.1:5000/register")

if __name__ == "__main__":
    generate_invite()
