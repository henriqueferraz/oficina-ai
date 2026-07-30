/**
 * Máscaras de formulário — telefone BR e CPF.
 * Telefone: (XX) XXXX-XXXX | (XX) XXXXX-XXXX
 * CPF: 000.000.000-00
 */
(function () {
  function soDigitos(valor) {
    return String(valor || "").replace(/\D+/g, "");
  }

  function formatarTelefone(valor) {
    var d = soDigitos(valor).slice(0, 11);
    if (!d) return "";
    if (d.length <= 2) return "(" + d;
    var ddd = d.slice(0, 2);
    var num = d.slice(2);
    if (num.length <= 4) return "(" + ddd + ") " + num;
    if (d.length <= 10) {
      return "(" + ddd + ") " + num.slice(0, 4) + "-" + num.slice(4);
    }
    return "(" + ddd + ") " + num.slice(0, 5) + "-" + num.slice(5);
  }

  function formatarCpf(valor) {
    var d = soDigitos(valor).slice(0, 11);
    if (!d) return "";
    if (d.length <= 3) return d;
    if (d.length <= 6) return d.slice(0, 3) + "." + d.slice(3);
    if (d.length <= 9) {
      return d.slice(0, 3) + "." + d.slice(3, 6) + "." + d.slice(6);
    }
    return (
      d.slice(0, 3) +
      "." +
      d.slice(3, 6) +
      "." +
      d.slice(6, 9) +
      "-" +
      d.slice(9)
    );
  }

  function aplicarMascara(input, formatar, attrs) {
    if (!input || input.dataset.maskBound) return;
    input.dataset.maskBound = "1";
    Object.keys(attrs || {}).forEach(function (k) {
      if (!input.getAttribute(k)) input.setAttribute(k, attrs[k]);
    });

    function atualizar() {
      var formatado = formatar(input.value);
      if (input.value !== formatado) input.value = formatado;
    }

    input.addEventListener("input", atualizar);
    input.addEventListener("blur", atualizar);
    atualizar();
  }

  function init(root) {
    var escopo = root || document;
    escopo
      .querySelectorAll('input[name="telefone"], input[data-mask="telefone"]')
      .forEach(function (el) {
        aplicarMascara(el, formatarTelefone, {
          inputmode: "tel",
          autocomplete: "tel",
          placeholder: "(11) 98765-4321",
          maxlength: "15",
        });
      });
    escopo
      .querySelectorAll('input[data-mask="cpf"], input[name="documento"][data-mask="cpf"]')
      .forEach(function (el) {
        aplicarMascara(el, formatarCpf, {
          inputmode: "numeric",
          placeholder: "000.000.000-00",
          maxlength: "14",
        });
      });
  }

  window.OficinaMasks = {
    formatarTelefone: formatarTelefone,
    formatarCpf: formatarCpf,
    init: init,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      init();
    });
  } else {
    init();
  }

  document.body.addEventListener("htmx:afterSwap", function (evt) {
    init(evt.target);
  });
})();
