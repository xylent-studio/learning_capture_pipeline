from som_seedtalent_capture.processing import (
    FakeOcrProvider,
    FakeTranscriptionProvider,
    LocalOcrStubProvider,
    LocalTranscriptionStubProvider,
)


def test_fake_processing_providers_return_high_confidence_results():
    ocr_result = FakeOcrProvider(text="Visible text", confidence=0.95).extract("C:/captures/frame.png")
    transcript_result = FakeTranscriptionProvider(text="Spoken text", confidence=0.94).transcribe(
        "C:/captures/audio.wav",
        capture_session_id="session-test",
    )

    assert ocr_result.text == "Visible text"
    assert ocr_result.confidence == 0.95
    assert transcript_result.segments[0].text == "Spoken text"
    assert transcript_result.segments[0].confidence == 0.94


def test_local_stub_processing_providers_return_repo_safe_placeholders():
    ocr_result = LocalOcrStubProvider().extract("C:/captures/frame.png")
    transcript_result = LocalTranscriptionStubProvider().transcribe(
        "C:/captures/audio.wav",
        capture_session_id="session-test",
    )

    assert ocr_result.provider_name == "local_ocr_stub"
    assert "stub output" in ocr_result.text.lower()
    assert transcript_result.provider_name == "local_transcription_stub"
    assert "stub output" in transcript_result.segments[0].text.lower()
