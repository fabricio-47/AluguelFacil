// Mensagens de validação de formulário em português, no padrão visual do
// Bootstrap (.was-validated / .invalid-feedback), em vez do balão nativo do
// navegador (que aparece em inglês). Funciona em qualquer <form> do sistema
// sem precisar editar o HTML de cada um.

(function () {
  function mensagemDeErro(campo) {
    if (campo.validity.valid) return "";

    if (campo.dataset.mensagemErro) return campo.dataset.mensagemErro;

    var tipo = (campo.type || "").toLowerCase();
    var v = campo.validity;

    if (v.valueMissing) {
      if (tipo === "checkbox" || tipo === "radio") return "Marque esta opção.";
      if (campo.tagName === "SELECT") return "Selecione uma opção.";
      return "Preencha este campo.";
    }
    if (v.typeMismatch) {
      if (tipo === "email") return "Digite um e-mail válido.";
      if (tipo === "url") return "Digite um endereço (URL) válido.";
      return "Digite um valor válido.";
    }
    if (v.patternMismatch) return campo.title || "O valor digitado não está no formato esperado.";
    if (v.tooShort) return "Digite pelo menos " + campo.minLength + " caracteres.";
    if (v.tooLong) return "Digite no máximo " + campo.maxLength + " caracteres.";
    if (v.rangeUnderflow) return "O valor mínimo é " + campo.min + ".";
    if (v.rangeOverflow) return "O valor máximo é " + campo.max + ".";
    if (v.stepMismatch) return "Digite um valor válido para este campo.";
    if (v.badInput) return "Digite um valor válido.";

    return "Verifique este campo.";
  }

  function garantirFeedback(campo) {
    var proximo = campo.nextElementSibling;
    if (proximo && proximo.classList && proximo.classList.contains("invalid-feedback")) {
      return proximo;
    }
    var div = document.createElement("div");
    div.className = "invalid-feedback";
    campo.insertAdjacentElement("afterend", div);
    return div;
  }

  function atualizarCampo(campo) {
    var msg = mensagemDeErro(campo);
    if (msg) {
      garantirFeedback(campo).textContent = msg;
    }
  }

  function tratarFormulario(form) {
    if (form.dataset.validacaoCustomizada) return; // formulário já cuida da própria validação
    form.setAttribute("novalidate", "novalidate");

    form.addEventListener(
      "input",
      function (ev) {
        if (form.classList.contains("was-validated")) {
          atualizarCampo(ev.target);
        }
      },
      true
    );

    form.addEventListener("submit", function (ev) {
      if (!form.checkValidity()) {
        ev.preventDefault();
        ev.stopPropagation();
        var invalidos = form.querySelectorAll(":invalid");
        invalidos.forEach(atualizarCampo);
        form.classList.add("was-validated");
        if (invalidos.length) {
          invalidos[0].focus();
        }
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("form").forEach(tratarFormulario);
  });
})();
