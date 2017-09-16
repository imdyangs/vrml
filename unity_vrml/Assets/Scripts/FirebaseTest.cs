﻿using Firebase;
using Firebase.Storage;
using Firebase.Database;

using System;
using System.Collections;
using System.Collections.Generic;
using System.Threading.Tasks;
using System.Text;
using UnityEngine;
using UnityEngine.UI;
using Firebase.Unity.Editor;

public class FirebaseTest : MonoBehaviour
{
    DatabaseReference reference;

    Color defaultColor;
    Transform imagesHolder;
    Vector3 defaultScale;
    FirebaseStorage storage;
    public GameObject player;

    void Start()
    {
        imagesHolder = GameObject.Find("ImagesHolder").transform;
        defaultColor = Color.blue;
        defaultScale = new Vector3(0.01f, 0.01f, 0.01f);

        FirebaseApp.DefaultInstance.SetEditorDatabaseUrl("https://vrml-c8ee5.firebaseio.com/");
        storage = FirebaseStorage.DefaultInstance;
        reference = FirebaseDatabase.DefaultInstance.RootReference;
        reference.Child("images_similar_100").ChildChanged += HandleChildChanged;
       // reference.Child("message").ValueChanged += MsgChanged;
       // reference.Child("message").ChildChanged += TstMsgChanged;
    }

    private void writeBool(bool _state)
    {
        State state = new State(_state);
        string json = JsonUtility.ToJson(state);
        reference.Child("ml-state").SetRawJsonValueAsync(json);
    }

    void HandleChildAdded(object sender, ChildChangedEventArgs args)
    {
        if (args.DatabaseError != null)
        {
            Debug.LogError(args.DatabaseError.Message);
            return;
        }
        Debug.Log(args.Snapshot.Child("coordinates").Child("x").ToString() + ", " +
            args.Snapshot.Child("coordinates").Child("y").ToString() + ", " +
            args.Snapshot.Child("coordinates").Child("z").ToString());

        createCube(string2Vector3(args.Snapshot.Child("coordinates").Child("x").ToString(), 
            args.Snapshot.Child("coordinates").Child("y").ToString(), 
            args.Snapshot.Child("coordinates").Child("z").ToString()),
            args.Snapshot.Child("id").ToString().Replace(".png", ""));
    }

    string[] cubes;

    Vector3 string2Vector3(string x, string y, string z) {
        Debug.Log(x + ", " + y + ", " + z);
        Vector3 toRet = new Vector3(float.Parse(x), float.Parse(y), float.Parse(z));
        return toRet;
    }
    void HandleChildChanged(object sender, ChildChangedEventArgs args) {


        Debug.Log(args.Snapshot.GetRawJsonValue());

        //dataPoint[] dp = JsonUtility.FromJson<dataPoint>(args.Snapshot.GetRawJsonValue());
        //dp.coords = 
            /*updateCube(string2Vector3(args.Snapshot.Child("coordinates").Child("x").ToString(),
            args.Snapshot.Child("coordinates").Child("y").ToString(),
            args.Snapshot.Child("coordinates").Child("z").ToString()),
            args.Snapshot.Child("id").ToString().Replace(".png", ""),
            float.Parse(args.Snapshot.Child("distance").ToString()) * Color.red);*/
    }

    void createCube(Vector3 pos, string name)
    {
        GameObject c = GameObject.CreatePrimitive(PrimitiveType.Cube);
        c.transform.SetParent(imagesHolder);
        c.transform.localPosition = pos;
        c.transform.localScale = defaultScale;
        c.GetComponent<Renderer>().material.color = defaultColor;
        c.name = name;
        c.tag = "InteractionCube";

        // rigidbody, no gravity
        Rigidbody c_rigidbody = c.AddComponent<Rigidbody>();
        c_rigidbody.useGravity = false;
    }

    void updateCube(Vector3 pos, string name, Color color)
    {
        GameObject c = GameObject.Find(name);
        c.transform.localPosition = pos;
        c.GetComponent<Renderer>().material.color = color;
    }

    void getImageFromStorage(string imageId, string cubeid)
    {
        StorageReference reference = storage.GetReference("images/" + imageId + ".png");
        reference.GetDownloadUrlAsync().ContinueWith(task => {
            StartCoroutine(getImageViaWWW(task.Result.ToString(), cubeid));
        });
    }

    IEnumerator getImageViaWWW(string url, string cubeid) // change this
    {
        Texture2D tex;
        tex = new Texture2D(4, 4, TextureFormat.DXT1, false);
        WWW www = new WWW(url);
        yield return www;
        www.LoadImageIntoTexture(tex);
        GameObject.Find(cubeid).GetComponent<Renderer>().material.mainTexture = tex;
    }

    void MsgChanged(object sender, ValueChangedEventArgs args) {
        Debug.Log(args.Snapshot.Value.ToString());
    }

    void TstMsgChanged(object sender, ChildChangedEventArgs args) {
        Debug.Log(args.Snapshot.Value.ToString());
    }
}

public class State
{
    public bool state;
    public State()
    {
    }

    public State(bool state)
    {
        this.state = state;
    }
}
[Serializable]
public class dataPoint {
    public string id;
    public Coords coords;
    public float distance;
}
[Serializable]
public class Coords {
    public string x;
    public string y;
    public string z;
}

public static class JsonHelper {
    public static T[] FromJson<T>(string json) {
        Wrapper<T> wrapper = JsonUtility.FromJson<Wrapper<T>>(json);
        return wrapper.Items;
    }

    public static string ToJson<T>(T[] array) {
        Wrapper<T> wrapper = new Wrapper<T>();
        wrapper.Items = array;
        return JsonUtility.ToJson(wrapper);
    }

    public static string ToJson<T>(T[] array, bool prettyPrint) {
        Wrapper<T> wrapper = new Wrapper<T>();
        wrapper.Items = array;
        return JsonUtility.ToJson(wrapper, prettyPrint);
    }

    [Serializable]
    private class Wrapper<T> {
        public T[] Items;
    }
}