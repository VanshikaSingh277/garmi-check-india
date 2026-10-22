/* Scene art for the landing page: the matka mascot and dusk clouds, as inline SVG (no image files).
   Colours come from CSS variables (--matka-*, --cloud-*, --leaf-*, --drop-*) so both themes stay on palette.
   SCENE.mascot(id) / SCENE.clouds(id, layer): id keeps gradient ids unique when a scene is drawn twice. */
(function () {
  function stops(list) { return list.map(function (s) { return '<stop offset="' + s[0] + '" style="stop-color:var(' + s[1] + ')"/>'; }).join(""); }
  var LEAF = "M0 0C8-10 22-10 30 0C22 10 8 10 0 0Z", DROP = "M0-10C4-4 7 0 7 4A7 7 0 0 1-7 4C-7 0-4-4 0-10Z";
  /* moods follow the heat: happy (low / unknown), warm (moderate), hot (high / extreme) */
  var MOUTH = {
    happy: '<path d="M120 198Q130 208 140 198" fill="none" style="stroke:var(--face)" stroke-width="3.5" stroke-linecap="round"/>',
    warm: '<path d="M121 202Q130 205 139 202" fill="none" style="stroke:var(--face)" stroke-width="3.5" stroke-linecap="round"/>',
    hot: '<ellipse cx="130" cy="203" rx="6.5" ry="8" style="fill:var(--face)"/>'
  };
  var BROWS = '<path d="M92 160L114 153M168 160L146 153" fill="none" style="stroke:var(--face)" stroke-width="3.5" stroke-linecap="round"/>';
  function mascot(id, mood) {
    var b = "url(#" + id + "b)";
    mood = MOUTH[mood] ? mood : "happy";
    var drops = mood === "happy" ? [[58, 172, .9], [204, 222, .7], [196, 148, .6]] : [[58, 172, .9], [204, 222, .7], [196, 148, .6], [80, 120, .8], [178, 116, .9], [212, 186, .7]];
    return '<svg class="mascot-svg mood-' + mood + '" viewBox="0 0 260 300" aria-hidden="true" focusable="false"><defs>' +
      '<radialGradient id="' + id + 'b" cx="36%" cy="30%" r="78%">' + stops([[0, "--matka-lit"], [0.48, "--matka"], [1, "--matka-shade"]]) + "</radialGradient>" +
      '<radialGradient id="' + id + 'r" cx="45%" cy="25%" r="85%">' + stops([[0, "--matka-lit"], [1, "--matka"]]) + "</radialGradient>" +
      '<linearGradient id="' + id + 'l" x1="0" y1="0" x2="1" y2="1">' + stops([[0, "--leaf-lit"], [1, "--leaf"]]) + "</linearGradient>" +
      '<radialGradient id="' + id + 'd" cx="35%" cy="30%" r="70%">' + stops([[0, "--drop-lit"], [1, "--drop"]]) + "</radialGradient></defs>" +
      /* arms: one resting, one waving */
      '<path d="M44 206C30 214 20 226 14 240" fill="none" style="stroke:var(--matka)" stroke-width="20" stroke-linecap="round"/>' +
      '<path d="M218 178C234 166 244 148 250 128" fill="none" style="stroke:var(--matka)" stroke-width="20" stroke-linecap="round"/>' +
      /* neem sprig growing out of the mouth */
      '<path d="M134 74C136 56 142 38 152 18" fill="none" style="stroke:var(--leaf)" stroke-width="3.5" stroke-linecap="round"/>' +
      [[136, 58, 200, .85], [140, 48, -35, 1], [146, 34, 30, .9], [150, 22, -62, .8]].map(function (l) { return '<path d="' + LEAF + '" transform="translate(' + l[0] + " " + l[1] + ") rotate(" + l[2] + ") scale(" + l[3] + ')" fill="url(#' + id + 'l)"/>'; }).join("") +
      /* pot */
      '<path d="M100 80C100 98 92 106 78 114C44 132 28 164 28 198C28 250 72 286 130 286S232 250 232 198C232 164 216 132 182 114C168 106 160 98 160 80Z" fill="' + b + '"/>' +
      '<ellipse cx="130" cy="82" rx="41" ry="10" style="fill:var(--matka-shade)" opacity=".55"/>' +
      '<ellipse cx="130" cy="76" rx="44" ry="12" fill="url(#' + id + 'r)"/><ellipse cx="130" cy="74" rx="33" ry="7" style="fill:var(--matka-mouth)"/>' +
      '<ellipse cx="86" cy="142" rx="24" ry="12" transform="rotate(-28 86 142)" style="fill:var(--sheen)" opacity=".28"/>' +
      /* painted band, like a real matka */
      '<path d="M46 232Q68 220 90 232T134 232T178 232T220 232" fill="none" style="stroke:var(--sheen)" stroke-width="4" stroke-linecap="round" opacity=".7"/>' +
      [60, 82, 104, 126, 148, 170, 192].map(function (x) { return '<circle cx="' + x + '" cy="248" r="3" style="fill:var(--sheen)" opacity=".6"/>'; }).join("") +
      /* face; .pupils is nudged towards the pointer by app.js */
      '<g class="pupils"><ellipse cx="104" cy="178" rx="11" ry="14" style="fill:var(--face)"/><ellipse cx="156" cy="178" rx="11" ry="14" style="fill:var(--face)"/>' +
      '<circle cx="108" cy="172" r="3.6" style="fill:var(--sheen)"/><circle cx="160" cy="172" r="3.6" style="fill:var(--sheen)"/><circle cx="101" cy="184" r="1.6" style="fill:var(--sheen)"/><circle cx="153" cy="184" r="1.6" style="fill:var(--sheen)"/></g>' +
      '<ellipse cx="84" cy="200" rx="12" ry="6" style="fill:var(--blush)" opacity="' + (mood === "hot" ? ".9" : ".6") + '"/><ellipse cx="176" cy="200" rx="12" ry="6" style="fill:var(--blush)" opacity="' + (mood === "hot" ? ".9" : ".6") + '"/>' +
      (mood === "hot" ? BROWS : "") + MOUTH[mood] +
      /* cool-water droplets: a matka cools by sweating (more of them when it is hot) */
      drops.map(function (d) { return '<path d="' + DROP + '" transform="translate(' + d[0] + " " + d[1] + ") scale(" + d[2] + ')" fill="url(#' + id + 'd)"/>'; }).join("") +
      "</svg>";
  }
  /* fixed-seed random, so the clouds have the same shape on every load */
  function rng(seed) { return function () { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; }; }
  /* cumulus banks: overlapping rows of varied, top-lit puffs riding a gently rolling ridge; lower rows hide the
     shaded undersides of the row above, so the bank reads as one soft cloud rather than a row of balls */
  function clouds(id, layer) {
    var front = layer === "front", g = id + (front ? "f" : "k"), rand = rng(front ? 7 : 3), puffs = "";
    var rows = front ? [{ y: 214, a: 42, b: 74, s: 58 }, { y: 250, a: 46, b: 78, s: 64 }, { y: 286, a: 50, b: 80, s: 70 }]
      : [{ y: 150, a: 50, b: 98, s: 72 }, { y: 196, a: 56, b: 96, s: 78 }, { y: 240, a: 60, b: 92, s: 84 }];
    var ph = front ? 1.7 : 0.4;
    rows.forEach(function (row, k) {
      for (var x = -70 + rand() * 40; x < 1520; x += row.s * (0.65 + 0.6 * rand())) {
        var r = row.a + rand() * (row.b - row.a), cy = row.y + 30 * Math.sin(x / 230 + ph) + 14 * Math.sin(x / 97 + ph * 2) + rand() * 12 - k * 4;
        puffs += '<circle cx="' + x.toFixed(0) + '" cy="' + cy.toFixed(0) + '" r="' + r.toFixed(0) + '" fill="url(#' + g + ')"/>';
      }
    });
    var c = front ? [[0, "--cloud-lit"], [0.5, "--cloud-mid"], [1, "--cloud-shade"]] : [[0, "--cloud-mid"], [0.55, "--cloud-shade"], [1, "--cloud-deep"]];
    return '<svg class="clouds ' + (front ? "front" : "back") + '" viewBox="0 0 1440 300" preserveAspectRatio="xMidYMax slice" aria-hidden="true" focusable="false"><defs>' +
      '<radialGradient id="' + g + '" cx="46%" cy="16%" r="88%">' + stops(c) + "</radialGradient></defs>" + puffs + "</svg>";
  }
  window.SCENE = { mascot: mascot, clouds: clouds };
})();
