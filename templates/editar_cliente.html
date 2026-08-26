{% extends "base.html" %}

{% block content %}
<div class="container mt-4">
  <h1>Editar Cliente</h1>

  <!-- Exibe mensagens flash -->
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
      {% for category, message in messages %}
        <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
          {{ message }}
          <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
      {% endfor %}
    {% endif %}
  {% endwith %}

  <form method="POST" action="{{ url_for('clientes.editar_cliente', id=cliente.id) }}" enctype="multipart/form-data">
    <div class="row g-3">
      <div class="col-md-9 order-md-1">
        <div class="row g-3">
          <div class="col-md-6">
            <label for="nome" class="form-label">Nome *</label>
            <input type="text" class="form-control" id="nome" name="nome" value="{{ cliente.nome }}" required>
          </div>
          <div class="col-md-6">
            <label for="email" class="form-label">Email *</label>
            <input type="email" class="form-control" id="email" name="email" value="{{ cliente.email }}" required>
          </div>
          <div class="col-md-4">
            <label for="telefone" class="form-label">Telefone *</label>
            <input type="text" class="form-control" id="telefone" name="telefone" value="{{ cliente.telefone }}" required>
          </div>
          <div class="col-md-4">
            <label for="cpf" class="form-label">CPF</label>
            <input type="text" class="form-control" id="cpf" name="cpf" value="{{ cliente.cpf }}">
          </div>
          <div class="col-md-4">
            <label for="data_nascimento" class="form-label">Data de Nascimento</label>
            <input type="date" class="form-control" id="data_nascimento" name="data_nascimento" value="{{ cliente.data_nascimento }}">
          </div>
          <div class="col-12">
            <label for="endereco" class="form-label">Endereço</label>
            <input type="text" class="form-control" id="endereco" name="endereco" value="{{ cliente.endereco }}">
          </div>
          <div class="col-12">
            <label for="observacoes" class="form-label">Observações</label>
            <textarea class="form-control" id="observacoes" name="observacoes" rows="3">{{ cliente.observacoes }}</textarea>
          </div>

          {% for campo, coluna, rotulo in [
            ("doc_frente", "doc_frente_arquivo", "Documento com foto (frente)"),
            ("doc_verso", "doc_verso_arquivo", "Documento com foto (verso)"),
            ("comprovante_residencia", "comprovante_residencia_arquivo", "Comprovante de residência"),
          ] %}
          <div class="col-md-4">
            <label for="{{ campo }}" class="form-label">{{ rotulo }}</label>
            {% if cliente[coluna] %}
              <div class="mb-2">
                <img src="{{ url_for('clientes.uploaded_documento', cliente_id=cliente.id, filename=cliente[coluna]) }}"
                     class="img-fluid rounded border" style="max-height: 120px;" alt="{{ rotulo }}">
              </div>
            {% endif %}
            <input type="file" class="form-control" id="{{ campo }}" name="{{ campo }}" accept=".png,.jpg,.jpeg">
            {% if cliente[coluna] %}
              <button type="submit" form="excluir-{{ campo }}" class="btn btn-sm btn-outline-danger mt-1">Excluir</button>
            {% endif %}
          </div>
          {% endfor %}
        </div>
      </div>

      <div class="col-md-3 order-md-2">
        <label for="foto_cliente" class="form-label">Foto do cliente</label>
        <div id="foto_cliente_preview_box" class="border rounded d-flex align-items-center justify-content-center mb-2 text-muted" style="height: 160px;">
          {% if cliente.foto_cliente_arquivo %}
            {% if cliente.foto_cliente_arquivo.lower().endswith('.pdf') %}
              <a href="{{ url_for('clientes.uploaded_documento', cliente_id=cliente.id, filename=cliente.foto_cliente_arquivo) }}" target="_blank">Ver PDF</a>
            {% else %}
              <img src="{{ url_for('clientes.uploaded_documento', cliente_id=cliente.id, filename=cliente.foto_cliente_arquivo) }}"
                   class="img-fluid rounded" style="max-height: 160px;" alt="Foto do cliente">
            {% endif %}
          {% else %}
            Sem foto
          {% endif %}
        </div>
        <video id="foto_cliente_video" class="d-none w-100 rounded mb-2" autoplay playsinline></video>
        <canvas id="foto_cliente_canvas" class="d-none"></canvas>
        <input type="file" class="form-control mb-2" id="foto_cliente" name="foto_cliente" accept=".png,.jpg,.jpeg,.pdf" onchange="previewFotoCliente(this)">
        <div id="foto_cliente_webcam_controls">
          <button type="button" class="btn btn-outline-secondary btn-sm w-100" onclick="iniciarWebcamFotoCliente()">Usar webcam</button>
        </div>
        <div id="foto_cliente_webcam_captura_controls" class="d-none d-flex gap-1 mb-1">
          <button type="button" class="btn btn-success btn-sm" onclick="capturarFotoCliente()">Capturar</button>
          <button type="button" class="btn btn-outline-danger btn-sm" onclick="cancelarWebcamFotoCliente()">Cancelar</button>
        </div>
        {% if cliente.foto_cliente_arquivo %}
          <button type="submit" form="excluir-foto_cliente" class="btn btn-sm btn-outline-danger mt-1">Excluir</button>
        {% endif %}
      </div>
    </div>
    <div class="mt-3">
      <button type="submit" class="btn btn-success">Salvar Alterações</button>
      <a href="{{ url_for('clientes.listar_clientes') }}" class="btn btn-secondary">Cancelar</a>
    </div>
  </form>

  {% for campo, coluna, rotulo in [
    ("doc_frente", "doc_frente_arquivo", ""),
    ("doc_verso", "doc_verso_arquivo", ""),
    ("comprovante_residencia", "comprovante_residencia_arquivo", ""),
    ("foto_cliente", "foto_cliente_arquivo", ""),
  ] %}
    {% if cliente[coluna] %}
    <form id="excluir-{{ campo }}" method="POST"
          action="{{ url_for('clientes.excluir_documento', id=cliente.id, campo=campo) }}"
          onsubmit="return confirm('Excluir este documento?')"></form>
    {% endif %}
  {% endfor %}
</div>

<!-- Scripts extras, se você usa máscaras ou validações -->
<script>
  function previewFotoCliente(input) {
    var box = document.getElementById('foto_cliente_preview_box');
    if (!box) return;
    if (input.files && input.files[0]) {
      var file = input.files[0];
      if (file.type === 'application/pdf' || /\.pdf$/i.test(file.name)) {
        box.innerHTML = '<span>PDF selecionado: ' + file.name + '</span>';
      } else {
        var url = URL.createObjectURL(file);
        box.innerHTML = '<img src="' + url + '" class="img-fluid rounded" style="max-height: 160px;" alt="Foto do cliente">';
      }
    }
  }

  var fotoClienteStream = null;

  async function iniciarWebcamFotoCliente() {
    var video = document.getElementById('foto_cliente_video');
    var box = document.getElementById('foto_cliente_preview_box');
    try {
      fotoClienteStream = await navigator.mediaDevices.getUserMedia({ video: true });
    } catch (e) {
      alert('Não foi possível acessar a webcam: ' + e.message);
      return;
    }
    video.srcObject = fotoClienteStream;
    video.classList.remove('d-none');
    box.classList.add('d-none');
    document.getElementById('foto_cliente_webcam_controls').classList.add('d-none');
    document.getElementById('foto_cliente_webcam_captura_controls').classList.remove('d-none');
  }

  function pararWebcamFotoCliente() {
    if (fotoClienteStream) {
      fotoClienteStream.getTracks().forEach(function(t) { t.stop(); });
      fotoClienteStream = null;
    }
    document.getElementById('foto_cliente_video').classList.add('d-none');
    document.getElementById('foto_cliente_preview_box').classList.remove('d-none');
    document.getElementById('foto_cliente_webcam_controls').classList.remove('d-none');
    document.getElementById('foto_cliente_webcam_captura_controls').classList.add('d-none');
  }

  function cancelarWebcamFotoCliente() {
    pararWebcamFotoCliente();
  }

  function capturarFotoCliente() {
    var video = document.getElementById('foto_cliente_video');
    var canvas = document.getElementById('foto_cliente_canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(function(blob) {
      var file = new File([blob], 'webcam_foto_cliente.jpg', { type: 'image/jpeg' });
      var dt = new DataTransfer();
      dt.items.add(file);
      var input = document.getElementById('foto_cliente');
      input.files = dt.files;
      previewFotoCliente(input);
      pararWebcamFotoCliente();
    }, 'image/jpeg', 0.9);
  }

  document.addEventListener('DOMContentLoaded', function() {
    var telefoneInput = document.getElementById('telefone');
    var cpfInput = document.getElementById('cpf');

    if (telefoneInput) {
      telefoneInput.addEventListener('input', function() {
        this.value = this.value.replace(/\D/g, '').replace(/(\d{2})(\d)/, '($1) $2').replace(/(\d{4})(\d)/, '$1-$2');
      });
    }

    if (cpfInput) {
      cpfInput.addEventListener('input', function() {
        this.value = this.value.replace(/\D/g, '')
          .replace(/(\d{3})(\d)/, '$1.$2')
          .replace(/(\d{3})(\d)/, '$1.$2')
          .replace(/(\d{3})(\d{1,2})$/, '$1-$2');
      });
    }
  });
</script>
{% endblock %}
