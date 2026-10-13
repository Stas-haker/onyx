import { Text } from "@opal/components";

interface ProcessingStagesProps {
  status: string;
  stale: boolean;
}

const stages = [
  {
    key: "transcribe",
    label: "Распознавание речи",
    description: "Извлекаем аудио и распознаём речь с таймкодами.",
  },
  {
    key: "diarize",
    label: "Определение спикеров",
    description: "Разделяем реплики по участникам встречи.",
  },
  {
    key: "analyze",
    label: "Анализ встречи",
    description: "Готовим резюме, протокол, решения и поручения.",
  },
];

export default function ProcessingStages({
  status,
  stale,
}: ProcessingStagesProps) {
  const queued = status.startsWith("queued_");
  const current = stages.findIndex(
    (stage) => status === stage.key || status === `queued_${stage.key}`
  );
  const completed = status === "completed";
  const failed = status === "failed";
  const title = completed
    ? "Обработка завершена"
    : failed
      ? "Обработка остановлена с ошибкой"
      : current >= 0
        ? `Этап ${current + 1} из 3 · ${
            queued ? "Ожидание в очереди" : stages[current]!.label
          }`
        : "Статус обработки уточняется";

  return (
    <section className="meeting-stages space-y-3" aria-label="Этапы обработки">
      <div role="status" aria-live="polite" aria-atomic="true">
        <Text as="p" font="main-ui-action">
          {title}
        </Text>
        <Text as="p" font="secondary-body">
          {stale
            ? "Не удалось обновить статус. Показаны последние полученные данные."
            : failed
              ? "Точный этап сбоя не сохранён. Доступные результаты показаны ниже."
              : completed
                ? "Транскрипт и результаты анализа готовы."
                : current >= 0
                  ? queued
                    ? `Ожидаем свободный обработчик: ${stages[
                        current
                      ]!.label.toLocaleLowerCase()}.`
                    : stages[current]!.description
                  : "Ожидаем актуальные данные от сервера."}
        </Text>
      </div>
      <ol className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {stages.map((stage, index) => {
          const done = completed || (current >= 0 && index < current);
          const active = index === current;
          const state = done ? "done" : active ? "active" : "pending";
          return (
            <li
              key={stage.key}
              className="meeting-stage"
              data-state={state}
              aria-current={active ? "step" : undefined}
            >
              <Text as="p" font="main-ui-action">{`${index + 1}. ${
                stage.label
              }`}</Text>
              <Text as="p" font="secondary-body">
                {done
                  ? "Завершено"
                  : active
                    ? queued
                      ? "В очереди"
                      : "Выполняется"
                    : failed || current < 0
                      ? "Нет данных"
                      : "Впереди"}
              </Text>
            </li>
          );
        })}
      </ol>
      {!completed && !failed && current >= 0 && (
        <Text as="p" font="secondary-body">
          Статус обновляется автоматически. Длительность этапов различается;
          процент готовности и время до завершения пока недоступны.
        </Text>
      )}
    </section>
  );
}
