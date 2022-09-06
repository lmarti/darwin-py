import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Union

import deprecation

import darwin.datatypes as dt
from darwin.exporter.formats.numpy_encoder import NumpyEncoder
from darwin.version import __version__


def export(annotation_files: Iterable[dt.AnnotationFile], output_dir: Path) -> None:
    for id, annotation_file in enumerate(annotation_files):
        _export_file(annotation_file, id, output_dir)


def _export_file(annotation_file: dt.AnnotationFile, id: int, output_dir: Path):
    output: Dict[str, Any] = _build_json(annotation_file)
    output_file_path: Path = (output_dir / annotation_file.filename).with_suffix(".json")
    with open(output_file_path, "w") as f:
        json.dump(output, f, cls=NumpyEncoder, indent=1)


def _build_json(annotation_file: dt.AnnotationFile):
    if annotation_file.is_video:
        return _build_video_json(annotation_file)
    else:
        return _build_image_json(annotation_file)


def _build_image_json(annotation_file: dt.AnnotationFile):
    return {
        "image": {
            "seq": annotation_file.seq,
            "width": annotation_file.image_width,
            "height": annotation_file.image_height,
            "filename": annotation_file.filename,
            "original_filename": annotation_file.filename,
            "url": annotation_file.image_url,
            "thumbnail_url": annotation_file.image_thumbnail_url,
            "path": annotation_file.remote_path,
            "workview_url": annotation_file.workview_url,
        },
        "annotations": list(map(_build_annotation, annotation_file.annotations)),
    }


def _build_video_json(annotation_file: dt.AnnotationFile):
    return {
        "image": {
            "seq": annotation_file.seq,
            "frame_urls": annotation_file.frame_urls,
            "frame_count": len(annotation_file.frame_urls or []),
            "width": annotation_file.image_width,
            "height": annotation_file.image_height,
            "filename": annotation_file.filename,
            "original_filename": annotation_file.filename,
            "thumbnail_url": annotation_file.image_thumbnail_url,
            "url": annotation_file.image_url,
            "path": annotation_file.remote_path,
            "workview_url": annotation_file.workview_url,
        },
        "annotations": list(map(_build_annotation, annotation_file.annotations)),
    }


def _build_annotation(annotation):
    if isinstance(annotation, dt.VideoAnnotation):
        return _build_video_annotation(annotation)
    else:
        return _build_image_annotation(annotation)


def _build_author(author: dt.AnnotationAuthor) -> Dict[str, Any]:
    return {"full_name": author.name, "email": author.email}


def _build_sub_annotation(sub: dt.SubAnnotation) -> Dict[str, Any]:
    if sub.annotation_type == "instance_id":
        return {sub.annotation_type: {"value": sub.data}}
    elif sub.annotation_type == "attributes":
        return {sub.annotation_type: sub.data}
    elif sub.annotation_type == "text":
        return {sub.annotation_type: {"text": sub.data}}


def _build_authorship(annotation: Union[dt.VideoAnnotation, dt.Annotation]) -> Dict[str, Any]:
    annotators = {}
    if annotation.annotators:
        annotators = {"annotators": [_build_author(annotator) for annotator in annotation.annotators]}

    reviewers = {}
    if annotation.reviewers:
        reviewers = {"annotators": [_build_author(reviewer) for reviewer in annotation.reviewers]}

    return {**annotators, **reviewers}


def _build_video_annotation(annotation: dt.VideoAnnotation) -> Dict[str, Any]:
    return {
        **annotation.get_data(
            only_keyframes=False,
            post_processing=lambda annotation, _: _build_image_annotation(annotation, skip_slots=True),
        ),
        "name": annotation.annotation_class.name,
        "slot_names": annotation.slot_names,
        **_build_authorship(annotation),
    }


def _build_image_annotation(annotation: dt.Annotation, skip_slots: bool = False) -> Dict[str, Any]:
    json_subs = {}
    for sub in annotation.subs:
        json_subs.update(_build_sub_annotation(sub))

    base_json = {
        **json_subs,
        **_build_authorship(annotation),
        **_build_legacy_annotation_data(annotation.annotation_class, annotation.data),
        "name": annotation.annotation_class.name,
    }

    if skip_slots:
        return base_json
    else:
        return {**base_json, "slot_names": annotation.slot_names}


def _build_legacy_annotation_data(annotation_class: dt.AnnotationClass, data: Dict[str, Any]) -> Dict[str, Any]:
    if annotation_class.annotation_type == "complex_polygon":
        data["path"] = data["paths"][0]
        data["additional_paths"] = data["paths"][1:]
        del data["paths"]
        return {annotation_class.annotation_internal_type or "polygon": data}
    else:
        return {annotation_class.annotation_type: data}


DEPRECATION_MESSAGE = """

This function is going to be turned into private. This means that breaking 
changes in its interface and implementation are to be expected. We encourage using ``build_image_annotation`` 
instead of calling this low-level function directly.

"""


def build_image_annotation(annotation_file: dt.AnnotationFile) -> Dict[str, Any]:
    """
    Builds and returns a dictionary with the annotations present in the given file.

    Parameters
    ----------
    annotation_file: dt.AnnotationFile
        File with the image annotations to extract.

    Returns
    -------
    Dict[str, Any]
        A dictionary with the annotation from the given file. Has the following structure:

        .. code-block:: python

            {
                "annotations": [
                    {
                        "annotation_type": { ... }, # annotation_data
                        "name": "annotation class name",
                        "bounding_box": { ... } # Optional parameter, only present if the file has a bounding box as well
                    }
                ],
                "image": {
                    "filename": "a_file_name.json",
                    "height": 1000,
                    "width": 2000,
                    "url": "https://www.darwin.v7labs.com/..."
                }
            }
    """
    annotations: List[Dict[str, Any]] = []
    for annotation in annotation_file.annotations:
        payload = {
            annotation.annotation_class.annotation_type: _build_annotation_data(annotation),
            "name": annotation.annotation_class.name,
        }

        if (
            annotation.annotation_class.annotation_type == "complex_polygon"
            or annotation.annotation_class.annotation_type == "polygon"
        ) and "bounding_box" in annotation.data:
            payload["bounding_box"] = annotation.data["bounding_box"]

        annotations.append(payload)

    return {
        "annotations": annotations,
        "image": {
            "filename": annotation_file.filename,
            "height": annotation_file.image_height,
            "width": annotation_file.image_width,
            "url": annotation_file.image_url,
        },
    }


@deprecation.deprecated(
    deprecated_in="0.7.8",
    removed_in="0.8.0",
    current_version=__version__,
    details=DEPRECATION_MESSAGE,
)
def build_annotation_data(annotation: dt.Annotation) -> Dict[str, Any]:
    if annotation.annotation_class.annotation_type == "complex_polygon":
        return {"path": annotation.data["paths"]}

    if annotation.annotation_class.annotation_type == "polygon":
        return dict(filter(lambda item: item[0] != "bounding_box", annotation.data.items()))

    return dict(annotation.data)


def _build_annotation_data(annotation: dt.Annotation) -> Dict[str, Any]:
    if annotation.annotation_class.annotation_type == "complex_polygon":
        return {"path": annotation.data["paths"]}

    if annotation.annotation_class.annotation_type == "polygon":
        return dict(filter(lambda item: item[0] != "bounding_box", annotation.data.items()))

    return dict(annotation.data)
