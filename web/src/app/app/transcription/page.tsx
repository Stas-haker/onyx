"use client";

import { useRef, useState } from "react";
import useSWR from "swr";
import { Button, Text } from "@opal/components";
import { Content } from "@opal/layouts";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import { errorHandlingFetcher, skipRetryOnAuthError } from "@/lib/fetcher";
import type { Meeting } from "@/app/app/transcription/interfaces";
import "@/app/app/transcription/theme.css";

const labels: Record<string, string> = {
  queued_transcribe: "Ожидает транскрибации",
  transcribe: "Распознавание речи",
  queued_diarize: "Ожидает определения спикеров",
  diarize: "Определение спикеров",
  queued_analyze: "Ожидает анализа",
  analyze: "Анализ встречи",
  completed: "Готово",
  failed: "Ошибка обработки",
  agenda: "По повестке",
  off_topic: "Посторонние обсуждения",
  repeated: "Повторные обсуждения",
  unknown: "Не определено / паузы",
};

function time(seconds: number): string {
  return new Date(seconds * 1000).toISOString().slice(11, 19);
}

export default function TranscriptionPage() {
  const [selected, setSelected] = useState<string | null>(null);
  const [agenda, setAgenda] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const {
    data: meetings,
    error: listError,
    mutate: refreshList,
  } = useSWR<Meeting[]>(
    `/api/meetings?offset=${offset}`,
    errorHandlingFetcher,
    { refreshInterval: 5000, onErrorRetry: skipRetryOnAuthError }
  );
  const {
    data: meeting,
    error: detailError,
    mutate: refreshMeeting,
  } = useSWR<Meeting>(
    selected ? `/api/meetings/${selected}` : null,
    errorHandlingFetcher,
    { refreshInterval: 3000, onErrorRetry: skipRetryOnAuthError }
  );

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("agenda", agenda);
      const response = await fetch("/api/meetings", { method: "POST", body });
      if (!response.ok)
        throw new Error(
          "Не удалось загрузить файл. Проверьте размер файла и доступность модуля."
        );
      const created: Meeting = await response.json();
      setSelected(created.id);
      setQuery("");
      setOffset(0);
      await refreshList();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Ошибка загрузки");
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function retry() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/api/meetings/${selected}/retry`, {
        method: "POST",
      });
      if (!response.ok)
        throw new Error(
          "Повторный запуск недоступен: задача может ещё обрабатываться."
        );
      await refreshMeeting();
      await refreshList();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Ошибка повторного запуска"
      );
    } finally {
      setBusy(false);
    }
  }

  const analysis = meeting?.analysis;
  const segments = meeting?.segments.filter((segment) =>
    segment.text.toLocaleLowerCase().includes(query.toLocaleLowerCase())
  );

  return (
    <main
      className="miratorg-meetings flex-1 overflow-auto p-6 space-y-6"
      data-ph-no-capture
    >
      <Content
        sizePreset="headline"
        variant="section"
        title="MIRATORG · Транскрибация"
        description="Локальный архив встреч и решений"
      />
      <section className="meeting-panel space-y-4">
        <Text font="main-ui-action">Новая встреча</Text>
        <InputTypeIn
          aria-label="Повестка встречи"
          placeholder="Повестка: цели и вопросы встречи"
          value={agenda}
          maxLength={2000}
          onChange={(event) => setAgenda(event.target.value)}
        />
        <input
          ref={fileInput}
          type="file"
          hidden
          aria-label="Аудио или видео"
          accept="audio/*,video/*,.mkv,.avi,.m4a,.flac,.ogg"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void upload(file);
          }}
        />
        <Button onClick={() => fileInput.current?.click()} disabled={busy}>
          {busy ? "Загрузка…" : "Загрузить аудио или видео"}
        </Button>
        <Text font="secondary-body">
          MP3, WAV, M4A, OGG, FLAC, MP4, MKV, AVI, MOV, WebM. Загружайте записи,
          на обработку которых у вас есть право. Без повестки её соблюдение не
          оценивается.
        </Text>
      </section>
      {(error || listError || detailError) && (
        <div role="alert">
          <Text as="p">
            {error ||
              "Не удалось получить данные. Проверьте вход в систему и включение модуля."}
          </Text>
        </div>
      )}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <section className="meeting-panel space-y-3">
          <Text font="main-ui-action">Мои встречи</Text>
          {!meetings && !listError && <Text as="p">Загрузка списка…</Text>}
          {meetings?.length === 0 && (
            <Text as="p">Пока нет записей. Загрузите первую встречу.</Text>
          )}
          {meetings?.map((item) => (
            <div key={item.id} className="space-y-1">
              <Button
                prominence={selected === item.id ? "primary" : "secondary"}
                onClick={() => {
                  setSelected(item.id);
                  setQuery("");
                }}
              >
                {item.filename}
              </Button>
              <Text font="secondary-body">
                {labels[item.status] || item.status}
              </Text>
            </div>
          ))}
          <div className="flex gap-2">
            <Button
              disabled={offset === 0}
              prominence="secondary"
              onClick={() => setOffset(Math.max(0, offset - 50))}
            >
              Назад
            </Button>
            <Button
              disabled={!meetings || meetings.length < 50}
              prominence="secondary"
              onClick={() => setOffset(offset + 50)}
            >
              Далее
            </Button>
          </div>
        </section>
        <section className="meeting-panel xl:col-span-2 space-y-5">
          {!selected && (
            <Text as="p">
              Выберите встречу для просмотра транскрипта и анализа.
            </Text>
          )}
          {selected && !meeting && !detailError && (
            <Text as="p">Загрузка встречи…</Text>
          )}
          {meeting && (
            <>
              <Content
                sizePreset="section"
                variant="section"
                title={meeting.filename}
                description={`${
                  labels[meeting.status] || meeting.status
                } · ${time(meeting.duration || 0)}`}
              />
              {meeting.error && (
                <div role="alert">
                  <Text as="p">
                    Обработка не завершена. Проверьте локальные модели, память
                    GPU и доступность сервисов.
                  </Text>
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <Button
                  href={`/api/meetings/${meeting.id}/export?format=txt`}
                  prominence="secondary"
                >
                  Экспорт TXT
                </Button>
                <Button
                  href={`/api/meetings/${meeting.id}/export?format=json`}
                  prominence="secondary"
                >
                  Экспорт JSON
                </Button>
                {(meeting.status === "failed" ||
                  meeting.status === "completed" ||
                  Date.now() - Date.parse(meeting.updated_at) >
                    25 * 3600000) && (
                  <Button onClick={() => void retry()} disabled={busy}>
                    {meeting.status === "completed"
                      ? "Повторить анализ"
                      : "Повторить обработку"}
                  </Button>
                )}
              </div>
              {analysis && (
                <>
                  <Content
                    sizePreset="section"
                    variant="section"
                    title={`Результативность: ${analysis.effectiveness_score}/100`}
                    description="Модельная оценка — требует проверки человеком"
                  />
                  <Text as="p">{analysis.explanation}</Text>
                  <Text as="p">{analysis.summary}</Text>
                  <div className="grid grid-cols-2 gap-3">
                    {Object.entries(analysis.percent).map(([key, value]) => (
                      <div key={key} className="meeting-metric">
                        <Text as="p">{`${labels[key] || key}: ${value}%`}</Text>
                      </div>
                    ))}
                  </div>
                  <Text font="secondary-body">
                    Доли рассчитаны от всей длительности записи. Неопределённое
                    время включает паузы и участки без классификации.
                  </Text>
                  <Text font="main-ui-action">Протокол</Text>
                  <Text as="p">{analysis.minutes}</Text>
                  <Text font="main-ui-action">Решения</Text>
                  {analysis.decisions.map((decision, index) => (
                    <Text key={index}>{decision}</Text>
                  ))}
                  <Text font="main-ui-action">Поручения</Text>
                  {analysis.actions.map((action, index) => (
                    <Text key={index}>{`${action.task} · ${
                      action.owner || "Ответственный не указан"
                    } · ${action.deadline || "Срок не указан"}`}</Text>
                  ))}
                  <Text font="main-ui-action">Темы и временные диапазоны</Text>
                  {analysis.topics.map((topic, index) => (
                    <div key={index}>
                      <Text as="p">{`${topic.title} · ${
                        labels[topic.category] || topic.category
                      }`}</Text>
                      <Text font="secondary-body">{`${topic.ranges
                        .map(
                          (range) => `${time(range.start)}–${time(range.end)}`
                        )
                        .join(", ")} · ${topic.explanation}`}</Text>
                    </div>
                  ))}
                </>
              )}
              <InputTypeIn
                aria-label="Поиск по транскрипту"
                placeholder="Поиск по транскрипту"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
              <div className="max-h-[36rem] overflow-auto space-y-3">
                {segments?.length === 0 && (
                  <Text as="p">Фрагменты не найдены.</Text>
                )}
                {segments?.map((segment, index) => (
                  <div key={index}>
                    <Text font="secondary-body">{`${time(segment.start)}–${time(
                      segment.end
                    )} · ${segment.speaker}`}</Text>
                    <Text as="p">{segment.text}</Text>
                  </div>
                ))}
              </div>
            </>
          )}
        </section>
      </div>
    </main>
  );
}
