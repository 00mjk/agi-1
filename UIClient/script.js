var Demo = {

  onResponse : function( response ) {
       var e = document.getElementById( "stepTarget" );
       var o = JSON.parse( response ); // parse into object
       // pick out property of object
       var kind = o.kind;
       var s = JSON.stringify( o );// back to string
       e.innerHTML = "Object: " + s;
  },

  onClick : function() {
    var xmlhttp = new XMLHttpRequest();
    xmlhttp.onreadystatechange = function() {
      if( xmlhttp.readyState==4 && xmlhttp.status==200 ) {
         console.log( "ready, successful" );
         Demo.onResponse( xmlhttp.responseText );
      }
    };

    var e = document.getElementById( "stepTarget" );
    e.innerHTML = "... sent request"

    var url = "http://localhost:9999/control/step";
    xmlhttp.open( "GET", url, true );
    xmlhttp.send();
  }
};