import json
import os
import shutil

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.database import get_db, SessionLocal
from app.models.document import Document
from app.models.course import Course
from app.models.user import User
from app.core.security import get_current_user
from app.models.study_room import StudyRoom
from app.models.study_room_message import StudyRoomMessage
from app.models.study_room_member import StudyRoomMember

from app.services.pdf_service import extract_text_from_pdf
from app.services.ai_service import LMStudioServiceError
from app.services.document_topic_service import generate_document_summary_stream


router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)
def _get_accessible_document(
    db: Session,
    document_id: int,
    current_user: User,
):
    document = (
        db.query(Document)
        .filter(Document.id == document_id)
        .first()
    )

    if document is None:
        return None

    # Dokümanın sahibi ise erişebilir
    owner = (
        db.query(Course)
        .filter(
            Course.id == document.course_id,
            Course.user_id == current_user.id,
        )
        .first()
    )

    if owner is not None:
        return document

    # Doküman bir Study Room'da paylaşılmış mı?
    shared_room = (
        db.query(StudyRoom)
        .join(
            StudyRoomMessage,
            StudyRoomMessage.room_id == StudyRoom.id,
        )
        .join(
            StudyRoomMember,
            StudyRoomMember.room_id == StudyRoom.id,
        )
        .filter(
            StudyRoomMessage.material_type == "document",
            StudyRoomMessage.material_id == document_id,
            StudyRoomMember.user_id == current_user.id,
            StudyRoomMember.is_active == True,
            StudyRoom.is_active == True,
        )
        .first()
    )

    if shared_room is not None:
        return document

    return None

# =========================================================
# PDF YÜKLE
# =========================================================

@router.post("/upload")
def upload_document(
    course_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    print("1 - upload endpoint başladı", flush=True)

    course = (
        db.query(Course)
        .filter(
            Course.id == course_id,
            Course.user_id == current_user.id
        )
        .first()
    )
    print("2 - course sorgusu bitti", flush=True)

    if course is None:
        raise HTTPException(
            status_code=404,
            detail="Course bulunamadı."
        )

    os.makedirs("uploads", exist_ok=True)

    file_path = f"uploads/{file.filename}"

    print("3 - dosya kaydetme başlıyor", flush=True)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    print("4 - dosya kaydedildi", flush=True)

    print("5 - PDF text çıkarma başlıyor", flush=True)
    text, page_count = extract_text_from_pdf(file_path)
    print(
        f"6 - PDF text çıkarıldı: page_count={page_count}, chars={len(text)}",
        flush=True
    )

    new_document = Document(
        filename=file.filename,
        file_path=file_path,
        text=text,
        summary=None,
        page_count=page_count,
        course_id=course_id
    )

    print("9 - document DB kaydı başlıyor", flush=True)
    db.add(new_document)
    db.commit()
    print("10 - document DB kaydı tamamlandı", flush=True)
    db.refresh(new_document)

    return {
        "message": "PDF başarıyla yüklendi.",
        "document_id": new_document.id,
        "filename": new_document.filename,
        "page_count": new_document.page_count,
        "summary": new_document.summary
    }


def _sse_event(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


@router.get("/{document_id}/summary/stream")
def stream_document_summary(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    document = _get_accessible_document(
    db,
    document_id,
    current_user,
)

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document bulunamadı."
        )

    if not document.text or not document.text.strip():
        raise HTTPException(
            status_code=422,
            detail="Document metni boş."
        )

    document_text = document.text

    def event_stream():
        stream_db = SessionLocal()
        final_summary = None

        try:
            for stream_event in generate_document_summary_stream(document_text):
                if stream_event["event"] == "complete":
                    final_summary = stream_event["final_summary"]
                    continue

                yield _sse_event(
                    stream_event["event"],
                    stream_event["data"],
                )

            if not final_summary or not final_summary.strip():
                raise LMStudioServiceError("LM Studio boş özet oluşturdu.")

            stream_document = (
                stream_db.query(Document)
                .filter(Document.id == document_id)
                .first()
            )

            if stream_document is None:
                raise ValueError("Document artık mevcut değil.")

            stream_document.summary = final_summary
            stream_db.commit()

            yield _sse_event("done", {"status": "completed"})

        except (LMStudioServiceError, ValueError) as error:
            stream_db.rollback()
            print(f"ÖZETLEME STREAM HATASI: {repr(error)}", flush=True)
            yield _sse_event(
                "error",
                {
                    "status": "failed",
                    "message": "Özet oluşturulurken bir hata oluştu. Tekrar deneyebilirsiniz."
                },
            )

        except Exception as error:
            stream_db.rollback()
            print(f"BEKLENMEYEN STREAM HATASI: {repr(error)}", flush=True)
            yield _sse_event(
                "error",
                {
                    "status": "failed",
                    "message": "Özet oluşturulurken bir hata oluştu. Tekrar deneyebilirsiniz."
                },
            )

        finally:
            stream_db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# =========================================================
# KULLANICININ TÜM PDF'LERİNİ GETİR
# =========================================================

@router.get("/")
def get_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    documents = (
        db.query(
            Document.id,
            Document.filename,
            Document.uploaded_at,
            Document.course_id,
            Document.page_count,
        )
        .join(Course, Document.course_id == Course.id)
        .filter(Course.user_id == current_user.id)
        .all()
    )

    return [
        {
            "id": document_id,
            "filename": filename,
            "uploaded_at": uploaded_at,
            "course_id": course_id,
            "page_count": page_count,
        }
        for (
            document_id,
            filename,
            uploaded_at,
            course_id,
            page_count,
        ) in documents
    ]


# =========================================================
# TEK BİR PDF'Yİ GETİR
# =========================================================

@router.get("/{document_id}")
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    document = _get_accessible_document(
    db,
    document_id,
    current_user,
)
    

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document bulunamadı."
        )

    return document

# ============================================================
# TÜM YÜKLENEN İÇERİKLERİ TEMİZLE
# ============================================================

@router.delete("/clear")
def clear_uploaded_content(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    documents = (
        db.query(Document)
        .join(Course, Document.course_id == Course.id)
        .filter(
            Course.user_id == current_user.id
        )
        .all()
    )

    deleted_count = 0

    for document in documents:
        if document.file_path and os.path.exists(document.file_path):
            os.remove(document.file_path)

        db.delete(document)
        deleted_count += 1

    db.commit()

    return {
        "message": "Yüklenen içerikler başarıyla temizlendi.",
        "deleted_documents": deleted_count
    }
# =========================================================
# PDF SİL
# =========================================================

@router.delete("/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    document = (
        db.query(Document)
        .join(Course, Document.course_id == Course.id)
        .filter(
            Document.id == document_id,
            Course.user_id == current_user.id
        )
        .first()
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document bulunamadı."
        )

    # Fiziksel PDF dosyasını sil
    if os.path.exists(document.file_path):
        os.remove(document.file_path)

    # Veritabanından sil
    db.delete(document)
    db.commit()

    return {
        "message": "Document başarıyla silindi.",
        "document_id": document_id
    }
