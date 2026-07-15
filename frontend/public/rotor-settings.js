// Yandex Rotor prerender waiter. Lives in its own file because the site CSP
// (script-src 'self') forbids inline scripts.
window.YandexRotorSettings = {
  WaiterEnabled: true,
  FailOnTimeout: false,
  NoJsRedirectsToMain: true,
  IsLoaded: function () {
    return Boolean(document.querySelector('#root main'));
  }
};
