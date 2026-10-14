from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

import store
from auth import current_uid
from schemas import PhraseList

router = APIRouter()


@router.get("/phrases")
async def get_phrases(uid: str = Depends(current_uid)):
    return {"phrases": await run_in_threadpool(store.get_phrases, uid)}


@router.put("/phrases")
async def put_phrases(body: PhraseList, uid: str = Depends(current_uid)):
    phrases = [p.model_dump() for p in body.phrases]
    await run_in_threadpool(store.replace_phrases, uid, phrases)
    return {"phrases": phrases}
