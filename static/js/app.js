/**
 * Grade Predictor & What-If Analyzer — Frontend
 */

class GradePredictor {
  constructor() {
    this.gradingPolicy = null;
    this.gradesByCategory = null;
    this.allGrades = null;
    this.currentGrade = null;
    this.charts = {};
    this.currentPanel = 1;
    this.whatIfDebounceTimer = null;

    this.CATEGORY_COLORS = [
      '#0071e3', '#34c759', '#ff9500', '#ff3b30',
      '#5856d6', '#ff2d55', '#af52de', '#5ac8fa',
      '#ffcc00', '#4cd964',
    ];

    this.init();
  }

  // ── Initialization ──────────────────────────────────────────────────────

  init() {
    this.setupSyllabusUpload();
    this.setupGradesUpload();
  }

  // ── Navigation ──────────────────────────────────────────────────────────

  goToPanel(n) {
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.getElementById(`panel-${n}`).classList.add('active');

    document.querySelectorAll('.step-item').forEach(el => {
      const step = parseInt(el.dataset.step);
      el.classList.remove('active', 'complete');
      if (step === n) el.classList.add('active');
      else if (step < n) el.classList.add('complete');
    });

    this.currentPanel = n;
    window.scrollTo(0, 0);
  }

  // ── Error Banner ────────────────────────────────────────────────────────

  showError(message) {
    const banner = document.getElementById('error-banner');
    document.getElementById('error-message').textContent = message;
    banner.classList.remove('hidden');
  }

  hideError() {
    document.getElementById('error-banner').classList.add('hidden');
  }

  // ── Panel 1: Syllabus Upload ────────────────────────────────────────────

  setupSyllabusUpload() {
    const dropZone = document.getElementById('syllabus-drop-zone');
    const fileInput = document.getElementById('syllabus-file-input');

    dropZone.addEventListener('dragover', e => {
      e.preventDefault();
      dropZone.classList.add('drag-over');
    });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
    dropZone.addEventListener('drop', e => {
      e.preventDefault();
      dropZone.classList.remove('drag-over');
      const file = e.dataTransfer.files[0];
      if (file) this.uploadSyllabus(file);
    });
    fileInput.addEventListener('change', () => {
      if (fileInput.files[0]) this.uploadSyllabus(fileInput.files[0]);
    });
  }

  async uploadSyllabus(file) {
    this.hideError();
    const loading = document.getElementById('syllabus-loading');
    const dropZone = document.getElementById('syllabus-drop-zone');

    dropZone.classList.add('hidden');
    loading.classList.remove('hidden');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('/api/upload-syllabus', { method: 'POST', body: formData });
      const json = await res.json();

      if (!res.ok) {
        this.showError(json.message || 'Failed to parse syllabus.');
        dropZone.classList.remove('hidden');
        loading.classList.add('hidden');
        return;
      }

      this.gradingPolicy = json.data;
      this.renderPolicyEditor(this.gradingPolicy);
      this.goToPanel(2);
    } catch (err) {
      this.showError('Network error: ' + err.message);
      dropZone.classList.remove('hidden');
    } finally {
      loading.classList.add('hidden');
    }
  }

  // ── Panel 2: Policy Editor ──────────────────────────────────────────────

  renderPolicyEditor(policy) {
    document.getElementById('course-name-display').textContent =
      policy.course_name || 'Unknown Course';

    const tbody = document.getElementById('policy-table-body');
    tbody.innerHTML = '';

    (policy.categories || []).forEach((cat, i) => {
      tbody.appendChild(this.createPolicyRow(cat, i));
    });

    this.renderGradeScaleEditor(policy.grade_scale);
    this.updateWeightSum();

    const warning = policy.weight_warning;
    const warnEl = document.getElementById('weight-warning');
    if (warning) {
      warnEl.textContent = '⚠ ' + warning;
      warnEl.classList.remove('hidden');
    } else {
      warnEl.classList.add('hidden');
    }
  }

  createPolicyRow(cat, index) {
    const tr = document.createElement('tr');
    tr.dataset.index = index;
    tr.innerHTML = `
      <td><input class="table-input" type="text" value="${this.esc(cat.name)}" onchange="app.updatePolicyRow(${index})" /></td>
      <td><input class="table-input weight-input" type="number" min="0" max="100" step="0.1"
                 value="${cat.weight ?? ''}" onchange="app.updatePolicyRow(${index}); app.updateWeightSum();" /></td>
      <td><input class="table-input" type="number" min="0" step="1"
                 value="${cat.num_items ?? ''}" placeholder="—" onchange="app.updatePolicyRow(${index})" /></td>
      <td>
        <select class="table-select" onchange="app.updatePolicyRow(${index})">
          <option value="none" ${cat.drop_policy?.type === 'none' ? 'selected' : ''}>None</option>
          <option value="drop_lowest" ${cat.drop_policy?.type === 'drop_lowest' ? 'selected' : ''}>Drop Lowest</option>
          <option value="drop_highest" ${cat.drop_policy?.type === 'drop_highest' ? 'selected' : ''}>Drop Highest</option>
        </select>
      </td>
      <td><input class="table-input" type="number" min="0" step="1"
                 value="${cat.drop_policy?.count ?? 0}" onchange="app.updatePolicyRow(${index})" /></td>
      <td><button class="btn-icon" title="Remove" onclick="app.removePolicyRow(${index})">✕</button></td>
    `;
    return tr;
  }

  updatePolicyRow(index) {
    const tbody = document.getElementById('policy-table-body');
    const row = tbody.querySelector(`tr[data-index="${index}"]`);
    if (!row) return;

    const inputs = row.querySelectorAll('input');
    const select = row.querySelector('select');

    this.gradingPolicy.categories[index] = {
      name: inputs[0].value,
      weight: parseFloat(inputs[1].value) || 0,
      num_items: inputs[2].value ? parseInt(inputs[2].value) : null,
      drop_policy: {
        type: select.value,
        count: parseInt(inputs[3].value) || 0,
      },
    };
  }

  addCategoryRow() {
    if (!this.gradingPolicy) return;
    const newCat = { name: 'New Category', weight: 0, num_items: null, drop_policy: { type: 'none', count: 0 } };
    this.gradingPolicy.categories.push(newCat);
    const index = this.gradingPolicy.categories.length - 1;
    const tbody = document.getElementById('policy-table-body');
    tbody.appendChild(this.createPolicyRow(newCat, index));
    this.updateWeightSum();
  }

  removePolicyRow(index) {
    this.gradingPolicy.categories.splice(index, 1);
    this.renderPolicyEditor(this.gradingPolicy);
  }

  updateWeightSum() {
    const total = (this.gradingPolicy?.categories || []).reduce(
      (sum, c) => sum + (parseFloat(c.weight) || 0), 0
    );
    const badge = document.getElementById('weight-sum-badge');
    badge.textContent = `Total: ${total.toFixed(1)}%`;
    badge.className = 'weight-sum-badge';
    if (Math.abs(total - 100) < 0.5) badge.classList.add('exact');
    else if (total > 100) badge.classList.add('over');
    else badge.classList.add('under');
  }

  renderGradeScaleEditor(scale) {
    const container = document.getElementById('grade-scale-editor');
    container.innerHTML = '';
    const defaultScale = { A: 93, B: 83, C: 73, D: 63, F: 0 };
    const s = scale || defaultScale;

    Object.entries(s).forEach(([letter, minPct]) => {
      const div = document.createElement('div');
      div.className = 'grade-scale-item';
      div.innerHTML = `
        <span class="grade-letter-badge">${letter}</span>
        <input class="table-input grade-scale-input" type="number" min="0" max="100"
               value="${minPct}" ${letter === 'F' ? 'disabled' : ''}
               onchange="app.updateGradeScale('${letter}', this.value)" />
        <span class="grade-scale-suffix">%+</span>
      `;
      container.appendChild(div);
    });
  }

  updateGradeScale(letter, value) {
    if (!this.gradingPolicy.grade_scale) {
      this.gradingPolicy.grade_scale = { A: 93, B: 83, C: 73, D: 63, F: 0 };
    }
    this.gradingPolicy.grade_scale[letter] = parseFloat(value) || 0;
  }

  confirmPolicy() {
    // Sync all rows before moving forward
    const rows = document.querySelectorAll('#policy-table-body tr');
    rows.forEach((row, i) => {
      const inputs = row.querySelectorAll('input');
      const select = row.querySelector('select');
      if (inputs.length < 4) return;
      this.gradingPolicy.categories[i] = {
        name: inputs[0].value,
        weight: parseFloat(inputs[1].value) || 0,
        num_items: inputs[2].value ? parseInt(inputs[2].value) : null,
        drop_policy: {
          type: select.value,
          count: parseInt(inputs[3].value) || 0,
        },
      };
    });
    this.goToPanel(3);
  }

  // ── Panel 3: Grades Upload ──────────────────────────────────────────────

  setupGradesUpload() {
    const dropZone = document.getElementById('grades-drop-zone');
    const fileInput = document.getElementById('grades-file-input');

    dropZone.addEventListener('dragover', e => {
      e.preventDefault();
      dropZone.classList.add('drag-over');
    });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
    dropZone.addEventListener('drop', e => {
      e.preventDefault();
      dropZone.classList.remove('drag-over');
      const file = e.dataTransfer.files[0];
      if (file) this.uploadGrades(file);
    });
    fileInput.addEventListener('change', () => {
      if (fileInput.files[0]) this.uploadGrades(fileInput.files[0]);
    });
  }

  async uploadGrades(file) {
    this.hideError();
    const loading = document.getElementById('grades-loading');
    const dropZone = document.getElementById('grades-drop-zone');

    dropZone.classList.add('hidden');
    loading.classList.remove('hidden');

    const formData = new FormData();
    formData.append('file', file);
    formData.append('grading_policy', JSON.stringify(this.gradingPolicy));

    try {
      const res = await fetch('/api/upload-grades', { method: 'POST', body: formData });
      const json = await res.json();

      if (!res.ok) {
        this.showError(json.message || 'Failed to parse grades.');
        dropZone.classList.remove('hidden');
        loading.classList.add('hidden');
        return;
      }

      this.allGrades = json.data.grades;
      this.gradesByCategory = json.data.grades_by_category;
      this.renderGradesEditor();
      this.goToPanel(4);
    } catch (err) {
      this.showError('Network error: ' + err.message);
      dropZone.classList.remove('hidden');
    } finally {
      loading.classList.add('hidden');
    }
  }

  // ── Panel 4: Grades Editor ──────────────────────────────────────────────

  renderGradesEditor() {
    const tbody = document.getElementById('grades-table-body');
    tbody.innerHTML = '';

    const categoryNames = (this.gradingPolicy?.categories || []).map(c => c.name);
    categoryNames.push('Uncategorized');

    this.allGrades.forEach((grade, i) => {
      const tr = document.createElement('tr');
      const statusOptions = ['graded', 'missing', 'excused', 'ungraded'];

      const catOptions = categoryNames
        .map(n => `<option value="${this.esc(n)}" ${n === grade.category ? 'selected' : ''}>${this.esc(n)}</option>`)
        .join('');

      const statusOptions2 = statusOptions
        .map(s => `<option value="${s}" ${s === grade.status ? 'selected' : ''}>${s.charAt(0).toUpperCase() + s.slice(1)}</option>`)
        .join('');

      tr.innerHTML = `
        <td>${this.esc(grade.assignment_name)}</td>
        <td>
          <select class="table-select" onchange="app.updateGradeCategory(${i}, this.value)">
            ${catOptions}
          </select>
        </td>
        <td><input class="table-input" type="number" min="0" step="0.5"
                   value="${grade.score_earned ?? ''}" placeholder="—"
                   onchange="app.updateGradeField(${i}, 'score_earned', this.value)" /></td>
        <td><input class="table-input" type="number" min="0" step="0.5"
                   value="${grade.max_score ?? ''}" placeholder="—"
                   onchange="app.updateGradeField(${i}, 'max_score', this.value)" /></td>
        <td>
          <select class="table-select" onchange="app.updateGradeField(${i}, 'status', this.value)">
            ${statusOptions2}
          </select>
        </td>
      `;
      tbody.appendChild(tr);
    });
  }

  updateGradeCategory(index, newCategory) {
    this.allGrades[index].category = newCategory;
  }

  updateGradeField(index, field, value) {
    if (field === 'score_earned' || field === 'max_score') {
      this.allGrades[index][field] = value ? parseFloat(value) : null;
    } else {
      this.allGrades[index][field] = value;
    }
  }

  confirmGrades() {
    // Rebuild gradesByCategory from the edited allGrades
    const categoryNames = (this.gradingPolicy?.categories || []).map(c => c.name);
    const grouped = {};
    categoryNames.forEach(n => { grouped[n] = []; });
    grouped['Uncategorized'] = [];

    this.allGrades.forEach(g => {
      const cat = g.category || 'Uncategorized';
      if (!grouped[cat]) grouped[cat] = [];
      grouped[cat].push(g);
    });

    if (!grouped['Uncategorized'].length) delete grouped['Uncategorized'];
    this.gradesByCategory = grouped;

    this.goToPanel(5);
    this.renderDashboard();
  }

  // ── Panel 5: Dashboard ──────────────────────────────────────────────────

  async renderDashboard() {
    try {
      const res = await fetch('/api/calculate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          grading_policy: this.gradingPolicy,
          grades_by_category: this.gradesByCategory,
        }),
      });
      const json = await res.json();
      if (!res.ok) { this.showError(json.message); return; }

      this.currentGrade = json.data;
      this.renderHeroStats(json.data);
      this.renderRiskFlags(json.data);
      this.renderDonutChart(json.data);
      this.renderBarChart(json.data);
      this.renderProgressBars(json.data);
      this.renderScenarioCards(json.data.scenarios);

      // Populate what-if panel
      this.populateWhatIfInputs();
      this.updateWhatIfDisplay(json.data);
    } catch (err) {
      this.showError('Failed to calculate grades: ' + err.message);
    }
  }

  renderHeroStats(data) {
    document.getElementById('hero-letter').textContent = data.letter_grade || '—';
    document.getElementById('hero-pct').textContent =
      data.overall_percentage != null ? `${data.overall_percentage.toFixed(2)}%` : '—';

    const buffer = data.points_buffer_before_drop;
    document.getElementById('hero-buffer').textContent =
      buffer != null ? `${buffer.toFixed(2)}%` : 'N/A';

    document.getElementById('hero-weight').textContent =
      data.total_weight_counted != null ? `${data.total_weight_counted}%` : '—';

    const letterEl = document.getElementById('hero-letter');
    const pct = data.overall_percentage || 0;
    letterEl.className = 'grade-hero-letter';
    if (pct >= 90) letterEl.classList.add('grade-a');
    else if (pct >= 80) letterEl.classList.add('grade-b');
    else if (pct >= 70) letterEl.classList.add('grade-c');
    else if (pct >= 60) letterEl.classList.add('grade-d');
    else letterEl.classList.add('grade-f');
  }

  renderRiskFlags(data) {
    const container = document.getElementById('risk-flags-container');
    container.innerHTML = '';

    Object.entries(data.per_category || {}).forEach(([catName, catData]) => {
      const pct = catData.percentage;
      if (pct == null) return;

      const weight = catData.weight;
      let flag = null;

      if (pct < 60 && weight >= 15) {
        flag = { level: 'critical', msg: `${catName}: ${pct.toFixed(1)}% — critically low in a ${weight}% category` };
      } else if (pct < 70 && weight >= 10) {
        flag = { level: 'warning', msg: `${catName}: ${pct.toFixed(1)}% — at risk (${weight}% of grade)` };
      }

      if (flag) {
        const div = document.createElement('div');
        div.className = `risk-flag ${flag.level}`;
        div.textContent = '⚠ ' + flag.msg;
        container.appendChild(div);
      }
    });
  }

  renderDonutChart(data) {
    const ctx = document.getElementById('donut-chart').getContext('2d');
    if (this.charts.donut) this.charts.donut.destroy();

    const categories = this.gradingPolicy?.categories || [];
    const labels = categories.map(c => c.name);
    const weights = categories.map(c => c.weight);
    const colors = labels.map((_, i) => this.CATEGORY_COLORS[i % this.CATEGORY_COLORS.length]);

    this.charts.donut = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data: weights,
          backgroundColor: colors,
          borderWidth: 2,
          borderColor: '#ffffff',
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { font: { family: '-apple-system, BlinkMacSystemFont, sans-serif', size: 12 } } },
          tooltip: {
            callbacks: {
              label: ctx => `${ctx.label}: ${ctx.parsed}%`,
            },
          },
        },
        cutout: '65%',
      },
    });
  }

  renderBarChart(data) {
    const ctx = document.getElementById('bar-chart').getContext('2d');
    if (this.charts.bar) this.charts.bar.destroy();

    const categories = this.gradingPolicy?.categories || [];
    const labels = categories.map(c => c.name);
    const currentPcts = labels.map(n => data.per_category[n]?.percentage ?? null);
    const colors = labels.map((_, i) => this.CATEGORY_COLORS[i % this.CATEGORY_COLORS.length]);

    // Threshold line at 90% (A boundary)
    const gradeScale = this.gradingPolicy?.grade_scale || { A: 93 };
    const aThreshold = gradeScale.A || 93;

    this.charts.bar = new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: 'Current %',
            data: currentPcts,
            backgroundColor: colors,
            borderRadius: 6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            min: 0, max: 100,
            ticks: { callback: v => v + '%' },
            grid: { color: '#e8e8ed' },
          },
          x: { grid: { display: false } },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => ctx.parsed.y != null ? `${ctx.parsed.y.toFixed(1)}%` : 'No grades yet',
            },
          },
          annotation: {
            annotations: {
              aLine: {
                type: 'line',
                yMin: aThreshold, yMax: aThreshold,
                borderColor: '#34c759',
                borderWidth: 1,
                borderDash: [6, 3],
                label: { display: true, content: 'A threshold', position: 'end' },
              },
            },
          },
        },
      },
    });
  }

  renderProgressBars(data) {
    const container = document.getElementById('category-progress-container');
    container.innerHTML = '';

    const categories = this.gradingPolicy?.categories || [];
    categories.forEach((cat, i) => {
      const catData = data.per_category?.[cat.name] || {};
      const pct = catData.percentage;
      const color = this.CATEGORY_COLORS[i % this.CATEGORY_COLORS.length];

      let statusClass = 'on-track';
      if (pct != null && pct < 60) statusClass = 'failing';
      else if (pct != null && pct < 75) statusClass = 'at-risk';

      const div = document.createElement('div');
      div.className = 'category-progress';
      div.innerHTML = `
        <div class="progress-header">
          <span class="progress-name">${this.esc(cat.name)}</span>
          <span class="progress-meta">
            ${pct != null ? pct.toFixed(1) + '%' : 'No grades'}
            &nbsp;·&nbsp; Weight: ${cat.weight}%
            ${catData.dropped_count ? `&nbsp;·&nbsp; ${catData.dropped_count} dropped` : ''}
            ${catData.missing_count ? `&nbsp;·&nbsp; ${catData.missing_count} missing` : ''}
          </span>
        </div>
        <div class="progress-track">
          <div class="progress-fill ${statusClass}"
               style="width: ${pct != null ? Math.min(pct, 100) : 0}%; background: ${color}"></div>
        </div>
      `;
      container.appendChild(div);
    });
  }

  renderScenarioCards(scenarios) {
    if (!scenarios) return;
    const container = document.getElementById('scenarios-container');
    container.innerHTML = '';

    const cards = [
      { key: 'best_case', label: 'Best Case', icon: '🚀', color: '#34c759' },
      { key: 'current_pace', label: 'Current Pace', icon: '📈', color: '#0071e3' },
      { key: 'worst_case', label: 'Worst Case', icon: '⚠', color: '#ff3b30' },
    ];

    cards.forEach(({ key, label, icon, color }) => {
      const s = scenarios[key];
      if (!s) return;
      const div = document.createElement('div');
      div.className = 'scenario-card';
      div.style.borderTop = `3px solid ${color}`;
      div.innerHTML = `
        <div class="scenario-icon">${icon}</div>
        <div class="scenario-label">${label}</div>
        <div class="scenario-grade" style="color: ${color}">${s.letter}</div>
        <div class="scenario-pct">${s.percentage != null ? s.percentage.toFixed(1) + '%' : '—'}</div>
        <div class="scenario-sub">${s.score_on_remaining != null ? s.score_on_remaining.toFixed(0) + '% on remaining' : ''}</div>
      `;
      container.appendChild(div);
    });
  }

  // ── Panel 6: What-If Analyzer ───────────────────────────────────────────

  populateWhatIfInputs() {
    const container = document.getElementById('whatif-assignments-container');
    container.innerHTML = '';

    const categories = this.gradingPolicy?.categories || [];

    categories.forEach(cat => {
      const allInCat = this.gradesByCategory?.[cat.name] || [];
      const ungraded = allInCat.filter(a => a.status === 'ungraded' || a.status === 'missing');

      // Also generate slots for num_items if defined
      const gradedCount = allInCat.filter(a => a.status === 'graded').length;
      const slotsFromPolicy = cat.num_items
        ? Math.max(0, cat.num_items - gradedCount)
        : 0;

      const remainingFromGrades = ungraded.map(a => ({
        name: a.assignment_name,
        max_score: a.max_score || 100,
        category: cat.name,
      }));

      // Add extra slots based on num_items
      for (let i = remainingFromGrades.length; i < slotsFromPolicy; i++) {
        remainingFromGrades.push({
          name: `${cat.name} (remaining ${i + 1})`,
          max_score: 100,
          category: cat.name,
        });
      }

      if (!remainingFromGrades.length) return;

      const section = document.createElement('div');
      section.className = 'whatif-category-section';
      section.innerHTML = `<h4 class="whatif-category-title">${this.esc(cat.name)}</h4>`;

      remainingFromGrades.forEach(asgn => {
        const row = document.createElement('div');
        row.className = 'whatif-row';
        const safeId = asgn.name.replace(/[^a-zA-Z0-9]/g, '_');
        row.innerHTML = `
          <label class="whatif-label">${this.esc(asgn.name)}</label>
          <input class="table-input whatif-input" type="number" min="0"
                 max="${asgn.max_score}" step="0.5" placeholder="Score (/${asgn.max_score})"
                 data-name="${this.esc(asgn.name)}"
                 data-max="${asgn.max_score}"
                 data-category="${this.esc(asgn.category)}"
                 onchange="app.onWhatIfChange()" />
        `;
        section.appendChild(row);
      });

      container.appendChild(section);
    });

    if (!container.children.length) {
      container.innerHTML = '<p class="panel-description">No remaining or ungraded assignments detected. Adjust scores in the grades editor.</p>';
    }
  }

  onWhatIfChange() {
    clearTimeout(this.whatIfDebounceTimer);
    this.whatIfDebounceTimer = setTimeout(() => this.recalculateWhatIf(), 300);
  }

  collectHypotheticalInputs() {
    const inputs = document.querySelectorAll('.whatif-input');
    const hyp = {};
    inputs.forEach(input => {
      if (input.value === '') return;
      hyp[input.dataset.name] = {
        score_earned: parseFloat(input.value),
        max_score: parseFloat(input.dataset.max),
        category: input.dataset.category,
      };
    });
    return hyp;
  }

  async recalculateWhatIf() {
    const hypotheticals = this.collectHypotheticalInputs();

    try {
      const res = await fetch('/api/what-if', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          grading_policy: this.gradingPolicy,
          grades_by_category: this.gradesByCategory,
          hypothetical_scores: hypotheticals,
        }),
      });
      const json = await res.json();
      if (res.ok) this.updateWhatIfDisplay(json.data);
    } catch (err) {
      // Silently fail on what-if recalc
    }
  }

  updateWhatIfDisplay(data) {
    document.getElementById('whatif-letter').textContent = data.letter_grade || '—';
    document.getElementById('whatif-pct').textContent =
      data.overall_percentage != null ? `${data.overall_percentage.toFixed(2)}%` : '—';

    const letterEl = document.getElementById('whatif-letter');
    const pct = data.overall_percentage || 0;
    letterEl.className = 'grade-hero-letter';
    if (pct >= 90) letterEl.classList.add('grade-a');
    else if (pct >= 80) letterEl.classList.add('grade-b');
    else if (pct >= 70) letterEl.classList.add('grade-c');
    else if (pct >= 60) letterEl.classList.add('grade-d');
    else letterEl.classList.add('grade-f');

    // Update scenario chart
    if (data.scenarios) this.renderScenarioLineChart(data.scenarios);
  }

  renderScenarioLineChart(scenarios) {
    const ctx = document.getElementById('scenario-chart').getContext('2d');
    if (this.charts.scenario) this.charts.scenario.destroy();

    const remaining = scenarios.remaining_count || 0;
    const labels = Array.from({ length: remaining + 1 }, (_, i) => `After ${i}`);

    const best = scenarios.best_case?.percentage;
    const worst = scenarios.worst_case?.percentage;
    const pace = scenarios.current_pace?.percentage;
    const current = this.currentGrade?.overall_percentage;

    const interpolate = (start, end, steps) =>
      steps <= 0 ? [start] :
      Array.from({ length: steps + 1 }, (_, i) => start + (end - start) * (i / steps));

    this.charts.scenario = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'Best Case',
            data: interpolate(current, best, remaining),
            borderColor: '#34c759',
            backgroundColor: 'transparent',
            borderWidth: 2,
            pointRadius: 3,
            tension: 0.3,
          },
          {
            label: 'Current Pace',
            data: interpolate(current, pace, remaining),
            borderColor: '#0071e3',
            backgroundColor: 'transparent',
            borderWidth: 2,
            pointRadius: 3,
            tension: 0.3,
          },
          {
            label: 'Worst Case',
            data: interpolate(current, worst, remaining),
            borderColor: '#ff3b30',
            backgroundColor: 'transparent',
            borderWidth: 2,
            borderDash: [5, 3],
            pointRadius: 3,
            tension: 0.3,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            min: Math.max(0, Math.floor((worst || 0) - 10)),
            max: 100,
            ticks: { callback: v => v + '%' },
            grid: { color: '#e8e8ed' },
          },
          x: { grid: { display: false } },
        },
        plugins: {
          legend: { position: 'bottom' },
          tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(1)}%` } },
        },
      },
    });
  }

  async calculateNeededScore() {
    const targetGrade = document.getElementById('target-grade-select').value;
    const resultCard = document.getElementById('needed-score-result');

    try {
      const res = await fetch('/api/needed-scores', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          grading_policy: this.gradingPolicy,
          grades_by_category: this.gradesByCategory,
          target_grade: targetGrade,
        }),
      });
      const json = await res.json();
      if (!res.ok) { this.showError(json.message); return; }

      const d = json.data;
      resultCard.classList.remove('hidden');

      if (d.is_achievable === false) {
        resultCard.innerHTML = `
          <div class="needed-score-header not-achievable">Not Achievable</div>
          <p>Even with 100% on all remaining work, the best possible grade is
             <strong>${d.best_possible?.toFixed(1)}%</strong>.</p>
        `;
      } else if (d.required_average == null) {
        resultCard.innerHTML = `
          <div class="needed-score-header achievable">Already There!</div>
          <p>Your current grade already meets the ${targetGrade} requirement.</p>
        `;
      } else {
        resultCard.innerHTML = `
          <div class="needed-score-header achievable">You Need a ${d.required_average?.toFixed(1)}%</div>
          <p>To earn an <strong>${targetGrade}</strong> (≥${d.target_percentage}%),
             you need an average of <strong>${d.required_average?.toFixed(1)}%</strong>
             on all remaining assignments.</p>
        `;
      }
    } catch (err) {
      this.showError('Calculation error: ' + err.message);
    }
  }

  // ── Utilities ───────────────────────────────────────────────────────────

  esc(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
}

// Bootstrap
const app = new GradePredictor();
