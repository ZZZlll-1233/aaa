/* pystrkit-web 前端逻辑。
 *
 * 约定：所有「即时计算」的工具卡都是 <div class="card" data-tool data-ep="...">，
 * 卡内 [data-arg="x"] 是入参，[data-out="x"] 是输出位，[data-meta] 是附加指标，
 * [data-err] 是错误位。所以这里没有任何针对某个接口的硬编码，加新接口只改 HTML。
 */
(function () {
  'use strict';

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  var BASE = window.location.origin;

  // ---------------------------------------------------------------- 工具函数
  function fmtValue(v) {
    if (v === null || v === undefined) return '—';
    if (v === true) return '是';
    if (v === false) return '否';
    return String(v);
  }

  function debounce(fn, wait) {
    var timer = null;
    return function () {
      var args = arguments, self = this;
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(self, args); }, wait);
    };
  }

  function api(path, payload) {
    var opts = { method: 'GET', headers: { 'Accept': 'application/json' } };
    if (payload !== undefined) {
      opts.method = 'POST';
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(payload);
    }
    return fetch(BASE + path, opts).then(function (resp) {
      return resp.json().catch(function () {
        return { ok: false, error: { message: '响应不是合法 JSON（HTTP ' + resp.status + '）' } };
      }).then(function (body) {
        if (!body || body.ok !== true) {
          var e = (body && body.error) || {};
          var err = new Error(e.message || '请求失败');
          err.code = e.code || 'unknown';
          throw err;
        }
        return body.data;
      });
    });
  }

  // ---------------------------------------------------------------- 工具卡
  function collectArgs(card) {
    var args = {};
    $$('[data-arg]', card).forEach(function (el) {
      var key = el.getAttribute('data-arg');
      var raw = el.value;
      // number 输入框交给后端校验，这里只在非空时转成数字，空字符串原样发过去让后端用默认值
      if (el.type === 'number') {
        args[key] = raw === '' ? '' : Number(raw);
      } else {
        args[key] = raw;
      }
    });
    return args;
  }

  function renderMeta(card, data) {
    var meta = $('[data-meta]', card);
    if (!meta) return;
    var spec = meta.getAttribute('data-meta') || '';
    if (!spec) { meta.innerHTML = ''; return; }
    var html = spec.split(',').map(function (pair) {
      var parts = pair.split(':');
      var key = parts[0], label = parts[1] || key;
      return '<span>' + label + ' <b>' + fmtValue(data[key]) + '</b></span>';
    }).join('');
    meta.innerHTML = html;
  }

  function runTool(card) {
    var ep = card.getAttribute('data-ep');
    var out = $('[data-out]', card);
    var errBox = $('[data-err]', card);
    var meta = $('[data-meta]', card);

    api(ep, collectArgs(card)).then(function (data) {
      if (errBox) errBox.classList.remove('show');
      if (out) {
        var key = out.getAttribute('data-out') || 'result';
        var text = fmtValue(data[key]);
        out.textContent = text;
        out.classList.toggle('empty', text === '' || text === '—');
      }
      if (meta) renderMeta(card, data);
    }).catch(function (err) {
      if (errBox) {
        errBox.textContent = err.message;
        errBox.classList.add('show');
      }
      if (meta) meta.innerHTML = '';
    });
  }

  function bindTools() {
    $$('[data-tool]').forEach(function (card) {
      var trigger = debounce(function () { runTool(card); }, 220);
      $$('[data-arg]', card).forEach(function (el) {
        el.addEventListener('input', trigger);
        el.addEventListener('change', trigger);
      });
      runTool(card);
    });
  }

  // ---------------------------------------------------------------- 示例填充
  var SAMPLES = {
    phones: '13812345678\n13900001111\n138-1234-5678\n12345\n18888888888',
    ids: '110101199003071234\n11010119900307123X\n123456\n11010119900307123',
    money: '1234.56\n100\n1.05\n-88.80\n9999999999999999.99\nabc',
    logs: '用户 13812345678 登录，身份证 110101199003071234\n' +
      '订单金额 1024.00 已支付\n' +
      '联系手机 13900001111，备用 13700002222'
  };

  function bindChips() {
    $$('[data-fill]').forEach(function (chip) {
      chip.addEventListener('click', function () {
        var target = document.getElementById(chip.getAttribute('data-fill'));
        if (!target) return;
        target.value = chip.getAttribute('data-value') || '';
        target.dispatchEvent(new Event('input', { bubbles: true }));
      });
    });
    $$('[data-batch-fill]').forEach(function (chip) {
      chip.addEventListener('click', function () {
        var key = chip.getAttribute('data-batch-fill');
        $('#batchIn').value = SAMPLES[key] || '';
      });
    });
  }

  // ---------------------------------------------------------------- 页签
  function bindTabs() {
    $$('.tabs button').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var name = btn.getAttribute('data-tab');
        $$('.tabs button').forEach(function (b) { b.classList.toggle('on', b === btn); });
        $$('.page').forEach(function (p) { p.classList.toggle('on', p.id === 'page-' + name); });
        if (name === 'api' && !$('#apiList').hasChildNodes()) loadApiDocs();
      });
    });
  }

  // ---------------------------------------------------------------- 批量
  var lastBatch = null;

  function batchOptions() {
    var fn = $('#batchFn').value;
    var opts = {};
    if (fn === 'truncate') opts.width = Number($('#batchWidth').value || 10);
    if (fn === 'phone') {
      opts.keep_head = Number($('#batchHead').value || 3);
      opts.keep_tail = Number($('#batchTail').value || 4);
    }
    if (fn === 'id-card') {
      opts.keep_head = Number($('#batchHead').value || 6);
      opts.keep_tail = Number($('#batchTail').value || 4);
    }
    return opts;
  }

  function syncBatchOptions() {
    var fn = $('#batchFn').value;
    $('#optWidth').style.display = fn === 'truncate' ? '' : 'none';
    var showHeadTail = (fn === 'phone' || fn === 'id-card');
    $('#optHead').style.display = showHeadTail ? '' : 'none';
    $('#optTail').style.display = showHeadTail ? '' : 'none';
    if (showHeadTail) {
      $('#batchHead').value = fn === 'phone' ? 3 : 6;
      $('#batchTail').value = 4;
    }
  }

  function renderBatch(data) {
    var rows = data.items.map(function (it) {
      if (it.ok) {
        return '<tr><td class="idx">' + it.index + '</td><td class="val">' +
          escapeHtml(it.input) + '</td><td class="val">' + escapeHtml(it.output) + '</td></tr>';
      }
      return '<tr class="fail"><td class="idx">' + it.index + '</td><td class="val">' +
        escapeHtml(it.input) + '</td><td class="val"><span class="tag">' +
        escapeHtml(it.error || '失败') + '</span></td></tr>';
    }).join('');

    $('#batchResult').innerHTML =
      '<table><thead><tr><th>#</th><th>输入</th><th>输出</th></tr></thead><tbody>' +
      rows + '</tbody></table>';

    var msg = '共 ' + data.total + ' 行';
    if (data.failed > 0) msg += '，失败 ' + data.failed + ' 行（标红）';
    $('#batchMeta').textContent = msg;
  }

  function escapeHtml(s) {
    return String(s === undefined || s === null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function bindBatch() {
    $('#batchFn').addEventListener('change', syncBatchOptions);
    $('#batchRun').addEventListener('click', function () {
      var errBox = $('#batchErr');
      errBox.classList.remove('show');
      api('/api/batch', {
        fn: $('#batchFn').value,
        text: $('#batchIn').value,
        options: batchOptions()
      }).then(function (data) {
        lastBatch = data;
        renderBatch(data);
      }).catch(function (err) {
        errBox.textContent = err.message;
        errBox.classList.add('show');
      });
    });

    $('#batchCopy').addEventListener('click', function () {
      if (!lastBatch) return;
      var text = lastBatch.items.map(function (it) { return it.ok ? it.output : ''; }).join('\n');
      copy(text, $('#batchCopy'));
    });

    $('#batchCsv').addEventListener('click', function () {
      if (!lastBatch) return;
      var lines = ['index,input,output,status'];
      lastBatch.items.forEach(function (it) {
        lines.push([it.index, csvCell(it.input), csvCell(it.output),
          it.ok ? 'ok' : csvCell(it.error)].join(','));
      });
      download('pystrkit-batch.csv', '\ufeff' + lines.join('\r\n'), 'text/csv');
    });

    syncBatchOptions();
  }

  function csvCell(v) {
    var s = String(v === undefined || v === null ? '' : v);
    return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }

  function copy(text, btn) {
    var done = function () {
      if (!btn) return;
      var old = btn.textContent;
      btn.textContent = '已复制';
      setTimeout(function () { btn.textContent = old; }, 1200);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, fallback);
    } else {
      fallback();
    }
    function fallback() {
      var ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); done(); } catch (e) { /* 忽略 */ }
      document.body.removeChild(ta);
    }
  }

  function download(name, content, type) {
    var blob = new Blob([content], { type: type + ';charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // ---------------------------------------------------------------- API 文档
  function curlFor(item) {
    var body = JSON.stringify(item.example || {});
    return 'curl -s ' + BASE + item.path + ' \\\n' +
      "  -H 'Content-Type: application/json' \\\n" +
      "  -d '" + body + "'";
  }

  function loadApiDocs() {
    api('/api/functions').then(function (data) {
      $('#apiList').innerHTML = data.items.map(function (it) {
        return '<div class="api-item">' +
          '<h4><span class="m">' + it.method + '</span> ' + escapeHtml(it.summary) +
          ' <span class="p">' + it.path + '</span></h4>' +
          '<p>' + escapeHtml(it.description || '') + '</p>' +
          '<pre>' + escapeHtml(curlFor(it)) + '</pre>' +
          '</div>';
      }).join('');
    }).catch(function (err) {
      $('#apiList').innerHTML = '<div class="err show">' + escapeHtml(err.message) + '</div>';
    });
  }

  // ---------------------------------------------------------------- 状态检测
  function checkHealth() {
    return api('/api/health').then(function (data) {
      $('#dot').className = 'dot on';
      $('#statusText').textContent = '后端已连接 · ' + data.endpoints + ' 个接口';
      return true;
    }).catch(function () {
      $('#dot').className = 'dot off';
      $('#statusText').textContent = '后端未连接，请确认服务已启动';
      return false;
    });
  }

  // ---------------------------------------------------------------- 启动
  document.addEventListener('DOMContentLoaded', function () {
    checkHealth().then(function (ok) {
      if (!ok) return;
      bindTools();
      bindChips();
      bindBatch();
      loadApiDocs();
    });
    bindTabs();
  });
})();
