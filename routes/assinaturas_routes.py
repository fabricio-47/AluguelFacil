import os

from flask import Blueprint, current_app, send_from_directory
from flask_login import login_required

from permissions import requer_permissao, VER_LOCACOES

assinaturas_bp = Blueprint("assinaturas", __name__, url_prefix="/assinaturas")


@assinaturas_bp.route("/<filename>")
@login_required
@requer_permissao(VER_LOCACOES)
def serve_assinatura(filename):
    pasta = os.path.join(current_app.config["UPLOAD_FOLDER"], "assinaturas")
    return send_from_directory(pasta, filename)
