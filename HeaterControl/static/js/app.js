$(document).ready(function(){

$('#togglePower').click(function(){
$("#togglePower").html('Sending...')
$("#togglePower").attr("disabled", true);
$.ajax({
  url: './toggle_power',
  success: function(msg){
      update_page(msg)
      $("#togglePower").attr("disabled", false);
      $("#togglePower").html('Toggle Power')
  },
  error: function(){
    swal('Error!', "Oopsy Woopsy we made a fucky wucky OwO");
    $("#togglePower`").attr("disabled", false);
    $("#togglePower").html('Toggle Power')
  }
});

});

$('#toggleHeat').click(function(){
$("#toggleHeat").html('Sending...')
$("#toggleHeat").attr("disabled", true);
$.ajax({
  url: './toggle_heat',
  success: function(msg){
      update_page(msg)
      $("#toggleHeat").attr("disabled", false);
      $("#toggleHeat").html('Toggle Heat')
  },
  error: function(){
    swal('Error!', "Oopsy Woopsy we made a fucky wucky OwO");
    $("#togglePower").attr("disabled", false);
    $("#togglePower").html('Toggle Heat')
  }
});

});




get_data()
});

function get_data(){
    setInterval(function(){
    $.ajax({
          type: 'POST',
          url: './',
          success: function(msg){
            update_page(msg)
          }
        });
    }, 5000)
}


function update_page(msg){
    status = msg['heater_status']['power'] ? 'on' : 'off'
    heat = msg['heater_status']['heat'] ? 'heated' : 'not heated'
    temp = msg['heater_status']['temp']
    hum = msg['heater_status']['hum']
    $("#curr_time").html(msg['time'])
    $("#power").html(status)
    $("#heated").html(heat)
    $("#temperature").html(temp+"°C")
    $("#humidity").html(hum+"%")
    document.title = temp+"°C "+hum+"%"

}
