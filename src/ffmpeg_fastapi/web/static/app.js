const FEATURES = {
  "sprite-form": "sprite",
  "images_to_video-form": "images_to_video",
};

function renderStatus(container, html) {
  container.innerHTML = html;
}

async function pollJob(container, jobId) {
  const res = await fetch(`/api/jobs/${jobId}`);
  const data = await res.json();

  if (data.status === "queued" || data.status === "running") {
    renderStatus(
      container,
      `<div class="flex items-center gap-2">
         <span class="loading loading-spinner loading-sm"></span>
         <span>${data.status}...</span>
       </div>`
    );
    setTimeout(() => pollJob(container, jobId), 1500);
    return;
  }

  if (data.status === "failed") {
    renderStatus(
      container,
      `<div class="alert alert-error"><span>Failed: ${data.error ?? "unknown error"}</span></div>`
    );
    return;
  }

  const resultUrl = `/api/jobs/${jobId}/result`;
  const isVideo = data.feature_name === "images_to_video";
  const preview = isVideo
    ? `<video src="${resultUrl}" controls class="max-w-full rounded"></video>`
    : `<img src="${resultUrl}" class="max-w-full rounded">`;

  renderStatus(
    container,
    `<div class="flex flex-col gap-3">
       ${preview}
       <a href="${resultUrl}" download class="btn btn-success btn-sm w-fit">Download</a>
     </div>`
  );
}

async function handleSubmit(event, featureName) {
  event.preventDefault();
  const form = event.target;
  const container = form.closest(".card-body").querySelector(".job-status");
  const submitButton = form.querySelector("button[type=submit]");

  renderStatus(container, `<span class="text-sm opacity-70">Uploading...</span>`);
  submitButton.disabled = true;

  try {
    const res = await fetch(`/api/jobs/${featureName}`, {
      method: "POST",
      body: new FormData(form),
    });
    if (!res.ok) {
      const err = await res.json();
      renderStatus(container, `<div class="alert alert-error"><span>${err.error ?? "request failed"}</span></div>`);
      return;
    }
    const { job_id } = await res.json();
    pollJob(container, job_id);
  } finally {
    submitButton.disabled = false;
  }
}

for (const [formId, featureName] of Object.entries(FEATURES)) {
  const form = document.getElementById(formId);
  form.addEventListener("submit", (event) => handleSubmit(event, featureName));
}
