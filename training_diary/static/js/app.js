const telegram = window.Telegram?.WebApp;
if (telegram) {
  telegram.ready();
  telegram.expand();
}

const initData = telegram?.initData || new URLSearchParams(window.location.search).get('initData') || '';

const elements = {
  exerciseSelect: document.getElementById('exerciseSelect'),
  addExerciseButton: document.getElementById('addExerciseButton'),
  dateInput: document.getElementById('dateInput'),
  timeOfDaySelect: document.getElementById('timeOfDaySelect'),
  weightInput: document.getElementById('weightInput'),
  repsInput: document.getElementById('repsInput'),
  logForm: document.getElementById('logForm'),
  historyContainer: document.getElementById('historyContainer'),
  exportButton: document.getElementById('exportButton'),
  toast: document.getElementById('toast'),
};

let loadByDayChart;
let loadByExerciseChart;

function showToast(message, tone = 'info') {
  const toast = elements.toast;
  toast.textContent = message;
  toast.classList.add('visible');
  setTimeout(() => toast.classList.remove('visible'), 2600);
}

function formatNumber(value) {
  return Number(value).toLocaleString('ru-RU', { maximumFractionDigits: 2 });
}

function translateTimeOfDay(value) {
  switch (value) {
    case 'morning':
      return 'утро';
    case 'afternoon':
      return 'день';
    case 'evening':
      return 'вечер';
    default:
      return value;
  }
}

async function apiFetch(path, { method = 'GET', body, headers } = {}) {
  const opts = { method, headers: { ...(headers || {}) } };
  if (initData) {
    opts.headers['X-Telegram-Init-Data'] = initData;
  }
  if (body && !(body instanceof FormData)) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
    if (!method || method === 'GET') {
      opts.method = 'POST';
    }
  }

  const response = await fetch(path, opts);
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (err) {
      console.error('Failed to parse response', err);
    }
  }
  if (!response.ok) {
    const message = data?.description || data?.message || 'Произошла ошибка запроса';
    throw new Error(message);
  }
  return data;
}

function getDefaultTimeOfDay() {
  const hour = new Date().getHours();
  if (hour < 12) return 'morning';
  if (hour < 17) return 'afternoon';
  return 'evening';
}

async function loadExercises() {
  try {
    const exercises = await apiFetch('/api/exercises');
    elements.exerciseSelect.innerHTML = '';
    if (!exercises || exercises.length === 0) {
      const option = document.createElement('option');
      option.value = '';
      option.textContent = 'Добавьте упражнение';
      elements.exerciseSelect.appendChild(option);
      return;
    }
    exercises.forEach((exercise) => {
      const option = document.createElement('option');
      option.value = exercise.id;
      option.textContent = exercise.name;
      elements.exerciseSelect.appendChild(option);
    });
  } catch (error) {
    showToast(error.message);
  }
}

async function promptNewExercise() {
  const name = window.prompt('Введите название упражнения');
  if (!name) {
    return;
  }
  try {
    const exercise = await apiFetch('/api/exercises', {
      method: 'POST',
      body: { name },
    });
    await loadExercises();
    elements.exerciseSelect.value = exercise.id;
    showToast('Упражнение сохранено');
  } catch (error) {
    showToast(error.message);
  }
}

function renderHistory(workouts) {
  const container = elements.historyContainer;
  container.innerHTML = '';
  if (!workouts || workouts.length === 0) {
    container.innerHTML = '<p>Пока нет записей. Начните с новой тренировки.</p>';
    return;
  }
  workouts.forEach((workout) => {
    const card = document.createElement('div');
    card.className = 'history-card';
    const header = document.createElement('div');
    header.className = 'card-header';
    header.innerHTML = `
      <h3>${workout.exercise}</h3>
      <div class="badge">${workout.performed_on} · ${translateTimeOfDay(workout.time_of_day)}</div>
    `;
    card.appendChild(header);

    const list = document.createElement('div');
    workout.sets.forEach((set) => {
      const row = document.createElement('div');
      row.className = 'set-row';
      row.innerHTML = `
        <span>Подход ${set.order}: ${set.reps} × ${formatNumber(set.weight)} кг</span>
        <div>
          <span class="badge">${formatNumber(set.load)}</span>
          <button type="button" data-set-id="${set.id}">Удалить</button>
        </div>
      `;
      const deleteButton = row.querySelector('button');
      deleteButton.addEventListener('click', async () => {
        try {
          await apiFetch(`/api/sets/${set.id}`, { method: 'DELETE' });
          showToast('Подход удалён');
          await refreshData();
        } catch (error) {
          showToast(error.message);
        }
      });
      list.appendChild(row);
    });

    card.appendChild(list);
    container.appendChild(card);
  });
}

async function loadHistory() {
  try {
    const workouts = await apiFetch('/api/workouts');
    renderHistory(workouts);
  } catch (error) {
    showToast(error.message);
  }
}

function buildDataset(entries, labelKey, valueKey) {
  return {
    labels: entries.map((entry) => entry[labelKey]),
    data: entries.map((entry) => entry[valueKey]),
  };
}

function updateChart(chart, canvasId, labels, data, options) {
  const ctx = document.getElementById(canvasId).getContext('2d');
  if (chart) {
    chart.data.labels = labels;
    chart.data.datasets[0].data = data;
    chart.update();
    return chart;
  }
  return new Chart(ctx, {
    type: options.type,
    data: {
      labels,
      datasets: [
        {
          label: options.label,
          data,
          borderColor: '#d62828',
          backgroundColor: options.type === 'bar' ? 'rgba(214, 40, 40, 0.6)' : 'rgba(214, 40, 40, 0.15)',
          tension: 0.3,
          fill: options.type !== 'bar',
        },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: { color: '#1f1f1f' },
        },
        x: {
          ticks: { color: '#1f1f1f' },
        },
      },
    },
  });
}

async function loadStats() {
  try {
    const dayData = await apiFetch('/api/stats/days');
    const exerciseData = await apiFetch('/api/stats/exercises');

    const dayDataset = buildDataset(dayData || [], 'date', 'load');
    const exerciseDataset = buildDataset(exerciseData || [], 'exercise', 'load');

    loadByDayChart = updateChart(loadByDayChart, 'loadByDayChart', dayDataset.labels, dayDataset.data, {
      type: 'line',
      label: 'Нагрузка',
    });

    loadByExerciseChart = updateChart(
      loadByExerciseChart,
      'loadByExerciseChart',
      exerciseDataset.labels,
      exerciseDataset.data,
      {
        type: 'bar',
        label: 'Нагрузка',
      },
    );
  } catch (error) {
    showToast(error.message);
  }
}

async function refreshData() {
  await Promise.all([loadExercises(), loadHistory(), loadStats()]);
}

elements.logForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const exerciseId = elements.exerciseSelect.value;
  const date = elements.dateInput.value;
  const timeOfDay = elements.timeOfDaySelect.value;
  const weight = Number(elements.weightInput.value);
  const reps = Number(elements.repsInput.value);

  if (!exerciseId) {
    showToast('Выберите упражнение или добавьте новое');
    return;
  }

  try {
    await apiFetch('/api/workouts', {
      method: 'POST',
      body: {
        exercise_id: Number(exerciseId),
        performed_on: date,
        time_of_day: timeOfDay,
        weight,
        reps,
      },
    });
    showToast('Подход сохранён');
    elements.weightInput.value = '';
    elements.repsInput.value = '';
    await refreshData();
  } catch (error) {
    showToast(error.message);
  }
});

elements.addExerciseButton.addEventListener('click', () => {
  promptNewExercise();
});

elements.exportButton.addEventListener('click', () => {
  const params = new URLSearchParams();
  const url = `/api/export${params.toString() ? `?${params.toString()}` : ''}`;
  fetch(url, {
    headers: initData ? { 'X-Telegram-Init-Data': initData } : {},
  })
    .then((response) => response.blob())
    .then((blob) => {
      const link = document.createElement('a');
      link.href = window.URL.createObjectURL(blob);
      link.download = 'training-log.csv';
      link.click();
      window.URL.revokeObjectURL(link.href);
    })
    .catch((error) => showToast(error.message || 'Не удалось экспортировать данные'));
});

function initialize() {
  const today = new Date().toISOString().split('T')[0];
  elements.dateInput.value = today;
  elements.timeOfDaySelect.value = getDefaultTimeOfDay();
  refreshData();
}

initialize();
